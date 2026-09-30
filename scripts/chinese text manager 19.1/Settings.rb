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
  FONT_NAME                 = Settings::GLOBAL_FONT_NAME
  SMALL_FONT_NAME           = Settings::GLOBAL_FONT_NAME
  NARROW_FONT_NAME          = Settings::GLOBAL_FONT_NAME
  FONT_Y_OFFSET             = Settings::Y_OFFSET_OF_TEXT
  SMALL_FONT_Y_OFFSET       = Settings::Y_OFFSET_OF_TEXT
  NARROW_FONT_Y_OFFSET      = Settings::Y_OFFSET_OF_TEXT
end