// 多言語タグ翻訳の単一実装（genai-tag-db TAG_TRANSLATIONS 相当）。
// SearchScreen の選択画像インスペクタと TagEditScreen の TAGS カードが共有する。
// 言語コードは DB 由来で en = danbooru canonical（= 保存値）。翻訳は表示のみで、
// 保存値は常に canonical 固定。trTag/hasTr は (lang, tag) を引数に取る純関数。
(function () {
  const LANGS = [
    { value: "en", label: "EN · canonical" },
    { value: "ja", label: "日本語 ja" },
    { value: "zh", label: "中文 zh" },
    { value: "zh-tw", label: "中文（繁）zh-tw" },
    { value: "ko", label: "한국어 ko" },
  ];
  const TAG_TR = {
    ja: { "1girl": "女性単独", "solo": "単独", "long_hair": "長い髪", "cherry_blossoms": "桜", "smile": "笑顔", "outdoors": "屋外", "tree": "木", "day": "昼", "hair_ornament": "髪飾り", "lens_flare": "レンズフレア", "blurry_background": "背景ぼけ", "looking_at_viewer": "カメラ目線", "upper_body": "上半身", "sky": "空" },
    zh: { "1girl": "1个女孩", "solo": "单人", "long_hair": "长发", "cherry_blossoms": "樱花", "smile": "微笑", "outdoors": "户外", "tree": "树", "day": "白天", "hair_ornament": "发饰", "lens_flare": "镜头光晕", "blurry_background": "背景模糊", "looking_at_viewer": "看向观众", "upper_body": "上半身", "sky": "天空" },
    "zh-tw": { "1girl": "1個女孩", "solo": "單人", "long_hair": "長髮", "cherry_blossoms": "櫻花", "smile": "微笑", "outdoors": "戶外", "tree": "樹", "day": "白天", "hair_ornament": "髮飾", "lens_flare": "鏡頭光暈", "blurry_background": "背景模糊", "looking_at_viewer": "看向觀眾", "upper_body": "上半身", "sky": "天空" },
    ko: { "1girl": "여자 1명", "solo": "솔로", "long_hair": "긴 머리", "cherry_blossoms": "벚꽃", "smile": "미소", "outdoors": "야외", "tree": "나무", "day": "낮", "hair_ornament": "머리 장식", "lens_flare": "렌즈 플레어", "blurry_background": "배경 흐림", "looking_at_viewer": "정면 응시", "upper_body": "상반신", "sky": "하늘" },
  };
  const trTag = (lang, t) => (lang === "en" ? t : ((TAG_TR[lang] && TAG_TR[lang][t]) || t));
  const hasTr = (lang, t) => lang === "en" || !!(TAG_TR[lang] && TAG_TR[lang][t]);
  window.LoRAIroTagI18n = { LANGS, TAG_TR, trTag, hasTr };
})();
