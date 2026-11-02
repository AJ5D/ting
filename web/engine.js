/* 面積與容積檢討表引擎（網頁版）。
 * 與 plugins/ting-area/skills/table-area/scripts/tingarea.py 同邏輯，
 * 算式與規則都讀同一份 rules/*.json；tests/test_web_engine.py 會比對兩邊每一格。 */
(function (root) {
  "use strict";
  var PING = 0.3025;
  var CITIES = { taipei: "臺北市", newtaipei: "新北市", taoyuan: "桃園市" };
  var TABLES = {
    site: "可建量試算",
    coverage: "建蔽率檢討",
    "per-floor-volume": "各層容積檢討",
    summary: "各層樓地板面積總表"
  };

  // RULES = { national, newtaipei, taipei, taoyuan, assumptions, formulas }，由頁面或測試注入
  function loadRules(RULES, city) {
    var out = {};
    var files = ["national"];
    if (city) {
      if (!CITIES[city]) throw new Error("不支援的縣市 " + city);
      files.push(city);
    }
    files.push("assumptions");
    files.forEach(function (name) {
      var data = RULES[name];
      Object.keys(data.params || {}).forEach(function (k) {
        var v = Object.assign({}, data.params[k]);
        if (!("source" in v)) v.source = data.name;
        out[k] = v;
      });
    });
    return out;
  }

  function excavationFormula(tiers) {
    var parts = [], lower = 0;
    tiers.forEach(function (t) {
      if (t.upto === null) {
        parts.push("MAX({usable}-" + lower + ",0)*" + t.ratio);
      } else {
        parts.push("MAX(MIN({usable}," + t.upto + ")-" + lower + ",0)*" + t.ratio);
        lower = t.upto;
      }
    });
    return "(" + parts.join("+") + ")/{usable}";
  }

  function round(x, n) {
    n = n || 0;
    var q = Math.pow(10, n);
    var v = Math.floor(Math.abs(x) * q + 0.5) / q * (x >= 0 ? 1 : -1);
    return v;
  }
  var FUNCS = {
    MIN: Math.min, MAX: Math.max, ROUND: round, INT: Math.floor,
    IF: function (c, a, b) { return c ? a : b; }
  };

  function Model() {
    this.defs = {};
    this.cache = {};
  }
  Model.prototype.const = function (k, v) { this.defs[k] = { c: v }; };
  Model.prototype.expr = function (k, t) { this.defs[k] = { e: t }; };
  Model.prototype.value = function (k) {
    if (k in this.cache) return this.cache[k];
    var d = this.defs[k];
    if (!d) throw new Error("未定義的項目 " + k);
    var val;
    if ("c" in d) {
      val = d.c;
    } else {
      var self = this;
      var js = d.e.replace(/\{(\w+)\}/g, function (_, key) { return "v(" + JSON.stringify(key) + ")"; });
      var fn = new Function("v", "MIN", "MAX", "ROUND", "INT", "IF", "return (" + js + ");");
      val = fn(function (key) { return self.value(key); }, FUNCS.MIN, FUNCS.MAX, FUNCS.ROUND, FUNCS.INT, FUNCS.IF);
    }
    this.cache[k] = val;
    return val;
  }

  function siteRows(F, bonuses) {
    var rows = F.site_head.map(function (r) { return r.slice(); });
    var keys = [];
    bonuses.forEach(function (b, i) {
      var t = F.site_bonus;
      rows.push([t[0].replace("@I@", i), b.name, t[2].replace("@I@", i), t[3], t[4]]);
      keys.push(rows[rows.length - 1][0]);
    });
    var sum = keys.map(function (k) { return "{" + k + "}"; }).join("+") || "0";
    F.site_tail.forEach(function (r) {
      rows.push([r[0], r[1], r[2].replace("@BONUS_SUM@", sum), r[3], r[4]]);
    });
    return rows;
  }

  function siteProblem(RULES, c) {
    var parcels = c.parcels || [];
    var blank = function (x) { return x === undefined || x === null || x === ""; };
    var i, k;
    var fields = [["area_m2", "面積"], ["coverage_ratio", "建蔽率"], ["far", "容積率"]];
    if (parcels.length) {
      for (i = 0; i < parcels.length; i++) {
        for (k = 0; k < fields.length; k++) {
          if (blank(parcels[i][fields[k][0]])) return (parcels[i].land_no || "第 " + (i + 1) + " 筆地號") + " 缺" + fields[k][1];
        }
      }
    } else {
      var site = c.site || {};
      var sf = [["area_m2", "基地面積"], ["coverage_ratio", "建蔽率"], ["far", "容積率"]];
      for (k = 0; k < sf.length; k++) if (blank(site[sf[k][0]])) return "缺" + sf[k][1];
    }
    var bm = c.basement || {};
    if ((bm.floors || 0) > 0 && blank(bm.excavation_ratio) && !("excavation_tiers" in loadRules(RULES, c.city)))
      return "這個縣市還沒有開挖率規則，請填開挖率";
    return null;
  }

  function check(RULES, c) {
    var floors = c.floors || [];
    var problem = siteProblem(RULES, c);
    var np = (c.parcels || []).length;
    var out = [["site", !problem, problem || (np ? np + " 筆地號合併計算" : "基地面積、容積率、建蔽率齊全")]];
    if (!c.building_area_m2) out.push(["coverage", false, "缺設計建築面積"]);
    else out.push(["coverage", !problem, problem ? "可建量試算做不出來" : "有設計建築面積"]);
    if (floors.length) {
      out.push(["per-floor-volume", true, floors.length + " 層資料"]);
      out.push(["summary", !problem, problem ? "可建量試算做不出來" : "全案一張"]);
    } else {
      out.push(["per-floor-volume", false, "缺各層面積"]);
      out.push(["summary", false, "缺各層面積"]);
    }
    return out;
  }

  // 回傳 { model, params, tables: {site: rows, coverage: rows, floors: [...], floorCols}, status }
  function compute(RULES, c) {
    var F = RULES.formulas;
    var status = check(RULES, c);
    var ok = {};
    status.forEach(function (s) { ok[s[0]] = s[1]; });

    var rules = loadRules(RULES, c.city);
    Object.keys(c.assumptions || {}).forEach(function (k) {
      if (!(k in rules)) throw new Error("assumptions 裡的 " + k + " 不是已知參數");
      rules[k] = Object.assign({}, rules[k], { value: c.assumptions[k], source: "案件檔覆寫", status: null });
    });
    var m = new Model();
    var s = c.site || {};
    var bm = c.basement || {};
    var parcels = c.parcels || [];
    var params = [];
    if (parcels.length) {
      // 多筆地號：面積相加，建蔽率、容積率以面積加權
      var terms = function (k) { return parcels.map(function (_, i) { return "{p" + i + "_area}*{p" + i + "_" + k + "}"; }).join("+"); };
      parcels.forEach(function (pc, i) {
        var name = (pc.land_no || "地號" + (i + 1)) + "（" + (pc.zone || "") + "）";
        m.const("p" + i + "_area", pc.area_m2); m.const("p" + i + "_cov", pc.coverage_ratio); m.const("p" + i + "_far", pc.far);
        params.push({ key: "p" + i + "_area", label: name + "面積", source: pc.source || "案件輸入" });
      });
      m.expr("site_area", parcels.map(function (_, i) { return "{p" + i + "_area}"; }).join("+"));
      m.expr("coverage", "(" + terms("cov") + ")/{site_area}");
      m.expr("far", "(" + terms("far") + ")/{site_area}");
    } else {
      m.const("site_area", s.area_m2);
      m.const("coverage", s.coverage_ratio);
      m.const("far", s.far);
    }
    m.const("reserved", s.reserved_m2 || 0);
    m.const("arcade", s.arcade_m2 || 0);
    m.const("basement_floors", bm.floors || 0);
    m.const("rooftop_floors", (c.rooftop || {}).floors || 0);
    var bonuses = c.bonuses || [];
    bonuses.forEach(function (b, i) { m.const("bonus_ratio_" + i, b.ratio); });
    Object.keys(rules).forEach(function (k) {
      if (k === "excavation_tiers") return;
      m.const(k, rules[k].value);
      params.push({ key: k, label: rules[k].label, source: rules[k].source, status: rules[k].status });
    });
    if (bm.excavation_ratio !== undefined && bm.excavation_ratio !== null) {
      m.const("excav_ratio", bm.excavation_ratio);
      params.push({ key: "excav_ratio", label: "地下開挖率", source: "案件輸入" });
    } else if (rules.excavation_tiers) {
      m.expr("excav_ratio", excavationFormula(rules.excavation_tiers.value));
      params.push({ key: "excav_ratio", label: rules.excavation_tiers.label,
        source: rules.excavation_tiers.source, status: rules.excavation_tiers.status });
    } else {
      m.const("excav_ratio", 0);
    }

    var tables = {};
    var site = siteRows(F, bonuses);
    site.forEach(function (r) { m.expr(r[0], r[2]); });
    if (ok.site) tables.site = site;
    if (ok.coverage) {
      m.const("cov_design", c.building_area_m2);
      F.coverage.forEach(function (r) { if (r[2]) m.expr(r[0], r[2]); });
      tables.coverage = F.coverage;
    }
    if (ok["per-floor-volume"]) {
      c.floors.forEach(function (fl, i) {
        var p = "f" + i + "_";
        m.const(p + "a0", fl.floor_area_m2 || 0);
        m.const(p + "bal", fl.balcony_m2 || 0);
        m.const(p + "lob", fl.lobby_m2 || 0);
        m.const(p + "oth", fl.other_exempt_m2 || 0);
        F.floor.forEach(function (col) {
          if (col[2]) m.expr(p + col[0], col[2].split("{%").join("{" + p));
        });
      });
      tables.floors = c.floors;
      tables.floorCols = F.floor;
    }
    if (ok.summary) {
      ["a0", "bal", "lob", "oth", "vol"].forEach(function (suf) {
        m.expr("sum_" + suf, c.floors.map(function (_, i) { return "{f" + i + "_" + suf + "}"; }).join("+"));
      });
      m.expr("sum_diff", "{allowed}-{sum_vol}");
      m.expr("sum_result", 'IF({sum_vol}<={allowed},"符合","超過")');
      tables.summary = true;
    }
    return { model: m, params: params, tables: tables, status: status };
  }

  var api = { PING: PING, CITIES: CITIES, TABLES: TABLES, loadRules: loadRules, check: check, compute: compute };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TingArea = api;
})(this);
