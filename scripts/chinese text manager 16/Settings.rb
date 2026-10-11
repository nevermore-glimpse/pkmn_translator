module Settings
	#字体垂直偏移量（默认为8，值越小文本向下）
	Y_OFFSET_OF_TEXT = 8
	
  #命令纠正偏移量(默认为8，值越小文本向下)
  Y_OFFSET_OF_ORDER_CORRCETION = 8

	#引号中填写自已使用的字体即可
	GLOBAL_FONT_NAME = "FusionPixelMonoPatched"
end
#=========================================================
# 以下内容禁止编辑
#=========================================================
module MessageConfig
  # 字体名：不同版本的引擎读的不是同一个常量 ——
  #   · Essentials v19 及以后：FONT_NAME / SMALL_FONT_NAME / NARROW_FONT_NAME
  #   · 老版（v18 及以前，例如 Void / 蛋白石 / 绿铀）：
  #     FontName / SmallFontName / NarrowFontName
  #     （它们的 pbDefaultSystemFontName 就是读 MessageConfig::FontName）
  # 两套都写上，否则「换了字体、某些游戏完全没反应」。
  # 先删掉同名旧常量再定义，免得 Ruby 报 already initialized constant。
  [:FONT_NAME, :SMALL_FONT_NAME, :NARROW_FONT_NAME,
   :FONTNAME, :SMALL_FONTNAME, :NARROWFONTNAME,
   :FontName, :SmallFontName, :NarrowFontName].each do |_pkmn_const|
    begin
      MessageConfig.module_eval("remove_const(:#{_pkmn_const})")
    rescue Exception
    end
    MessageConfig.const_set(_pkmn_const, Settings::GLOBAL_FONT_NAME)
  end
  FONT_Y_OFFSET             = Settings::Y_OFFSET_OF_TEXT
  SMALL_FONT_Y_OFFSET       = Settings::Y_OFFSET_OF_TEXT
  NARROW_FONT_Y_OFFSET      = Settings::Y_OFFSET_OF_TEXT
end