# ==============================================================================
# [pkmn] 中文文本处理 · Essentials 18.1 版（旧引擎 / Ruby 1.8 / RGSS1）
#
#   由「中文文本处理 v21.1」（作者：木亦会枯、楠楠楠小鸟）移植而来，
#   功能一致：中文逐字换行、字体替换、文本垂直偏移、地图文本去多余空格。
#
#   ★ 本文件是**生成物**：脚本 make_legacy_plugins.py 从官方 Essentials 18.1
#     的引擎源码里把下面这几个函数整份抠出来，再打上中文补丁拼成这一份，
#     跟目标引擎的实现逐行对齐（不同版本这几个函数体不一样）。
#     要改请改生成脚本，别手改这里。
#
#   ★ 这份脚本给**没有插件系统**的老游戏用（RPG Maker XP + RGSS，
#     Ruby 1.8.1）：它被直接插进 Scripts.rxdata、排在 Main 前面
#     （解包成 Data/Scripts/ 的游戏就是放一个排在 Main 前面的 .rb）。
#     —— 必须在 Main 之前：RGSS 从上往下执行脚本、读到 Main 就进游戏主循环，
#        挂在 Main 后面的脚本永远不会执行。
#
#   ★ 中文补丁做了什么：
#     ① 所有「把字符串切成一个个字符」的地方改走 _pkmn_chars()：
#        String#scan 配 /./m 是按 $KCODE 切的，RGSS / Ruby 1.8 默认不是 'U'，
#        汉字会被切成 3 个字节，ischinese? 永远判不出汉字 → 中文换行等于没生效；
#     ② 换行的断点：原版只在「空格之后的词首」记断点，中文没有空格 → 整行
#        被当成一个超长词、永不换行；这里让汉字逐字可断，非汉字照旧；
#     ③ getLineBrokenChunks / getLineBrokenText 的切词改成「连续非汉字算一个
#        词、汉字一字一词」（颜色码的位置仍按原词对齐）；
#     ④ pbDrawShadowText 里加整体垂直偏移（值在同目录 Settings.rb 里调）。
#
#   ★ 禁止手改本文件 —— 要改插件设置请改同目录的 Settings.rb。
# ==============================================================================

# [pkmn] Ruby 1.8 兼容补丁
#   旧版 RGSS（RPG Maker XP / 老 Essentials）跑的是 Ruby 1.8.1：
#     · String#ord        —— 1.8 根本没有（1.9 才加）
#     · String#each_char  —— 1.8.7 才加
#   这里补上。★ ord 必须用 unpack("U") 解出**真正的码点**：
#   1.8 的 self[0] 只给第一个字节（"中"[0] == 228），
#   拿它跟 0x4e00 比会永远判不出汉字，中文就换不了行。
# ------------------------------------------------------------------------------
if RUBY_VERSION.to_f < 1.9
  class String
    def ord
      self.unpack("U")[0] || 0
    end

    # ★ each_char 不能用 String#scan 配 /./m 那种写法：它按 $KCODE 决定
    #   怎么切，而 RGSS / Ruby 1.8 默认 $KCODE 不是 'U'（按字节切）——
    #   "中" 会被切成 3 个字节，后面 ischinese? 永远判不出汉字，
    #   中文换行就等于没生效。
    #   这里照着 UTF-8 的字节头自己走一遍，跟 $KCODE 无关，切出来的
    #   一定是完整的字符。
    def each_char
      bytes = self.unpack("C*")
      i = 0
      out = []
      while i < bytes.size
        b = bytes[i]
        len = b < 0x80 ? 1 : (b < 0xE0 ? 2 : (b < 0xF0 ? 3 : 4))
        len = bytes.size - i if i + len > bytes.size
        out << bytes[i, len].pack("C*")
        i += len
      end
      return out if !block_given?
      out.each { |c| yield c }
      self
    end
  end
end

# ------------------------------------------------------------------------------
# [pkmn] 把字符串切成「一个个字符」的数组
#   插件的换行逻辑全部建立在「一个汉字 = 一个字符」上，而 String#scan 配
#   /./m 那种写法是按 $KCODE 决定怎么切的：RGSS / Ruby 1.8 默认 $KCODE
#   不是 'U'（按字节切），
#   "中" 会被切成 3 段，后面 ischinese? 永远判不出汉字 —— 中文换行就等于没生效。
#   所以这里自己按 UTF-8 的字节头走一遍，跟 $KCODE 无关。
# ------------------------------------------------------------------------------
def _pkmn_chars(text)
  return text if text.is_a?(Array)     # 有的调用点传进来的已经是数组
  text = text.to_s
  return text.split(//) if RUBY_VERSION.to_f >= 1.9    # 1.9 起本来就是按字符切
  bytes = text.unpack("C*")
  out = []
  i = 0
  while i < bytes.size
    b = bytes[i]
    len = b < 0x80 ? 1 : (b < 0xE0 ? 2 : (b < 0xF0 ? 3 : 4))
    len = bytes.size - i if i + len > bytes.size
    out << bytes[i, len].pack("C*")
    i += len
  end
  return out
end

def ischinese?(char)
  # ★ 不走 String#ord：Ruby 1.8 没有它，而 1.8 的 char[0] 只给第一个字节。
  #   直接按 UTF-8 解出码点，1.8 / 1.9 以上都准。
  code = char.unpack("U")[0]
  return code != nil && code >= 0x4e00 && code <= 0x9fa5
end


# 旧版引擎从 v17 起就有 _MAPINTL，但有的整合版没有 MessageTypes ——
# 那就干脆别定义，免得引擎调用时找不到 MessageTypes 直接崩。
if defined?(MessageTypes) && MessageTypes.respond_to?(:getFromMapHash)
  PKMN_CN_SPACE_RE = begin
    Regexp.new("([\\p{Han}\\p{P}])\\s+([\\p{Han}\\p{P}])")
  rescue Exception
    nil
  end

  def _MAPINTL(mapid, *arg)
    string = MessageTypes.getFromMapHash(mapid, arg[0])
    string = string.clone
    (1...arg.length).each do |i|
      string.gsub!(/\{#{i}\}/, arg[i].to_s)
    end
    # ★ 去掉汉字/标点之间的多余空格。旧版 Oniguruma 可能不认 \p{Han}，
    #   所以正则改成运行时构造；构造不出来就跳过这一步
    #   （只影响「地图文本去空格」，换行与字体照旧）。
    string = string.gsub(PKMN_CN_SPACE_RE, '\1\2') if PKMN_CN_SPACE_RE
    return string
  end
end



# ------------------------------------------------------------------------------
# [pkmn] 不该出现在**行首**的字符（中文标点 / 收尾符号）
#   作者版的 1.3.8 专门修过「标点跑到行首」—— 换行时如果下一个字是这些，
#   就让它留在上一行末尾（宁可略微超出宽度）。这里用同一套思路。
# ------------------------------------------------------------------------------
PKMN_NO_LINE_START = "，。、；：？！）】》」』”’…—～·,.!?;:)]}"

def _pkmn_line_start_bad?(word)
  ch = _pkmn_chars(word)[0]
  return ch != nil && PKMN_NO_LINE_START.include?(ch)
end

# ------------------------------------------------------------------------------
# [pkmn] 把一段文本切成「词」（换行用）
#   连续的非汉字（英文单词 / 数字 / 空格 / 标点）算一个词，汉字**一个字一个词**。
#   原版按空格切词，中文整行没有空格 → 会被当成一个超长词，永远不换行。
# ------------------------------------------------------------------------------
def _pkmn_words(text)
  return [] if text == nil
  out = []
  buf = ""
  _pkmn_chars(text.to_s).each do |ch|
    if ischinese?(ch)
      out.push(buf) if buf != ""
      buf = ""
      out.push(ch)
    else
      buf += ch
    end
  end
  out.push(buf) if buf != ""
  return out
end

# ------------------------------------------------------------------------------
# [pkmn] 有颜色码时的切词：把每个词再按汉字拆开，颜色码**落在原词的最后一个字**上
#   —— 这样「从第几个字开始变色」和原版完全一致（原版是画完第 i 个词才换色）。
#   返回 [新词数组, 新颜色数组]。
# ------------------------------------------------------------------------------
def _pkmn_split_words(words, textcols)
  newwords = []
  newcols = []
  for i in 0...words.length
    parts = _pkmn_words(words[i])
    parts = [""] if parts.length == 0
    for j in 0...parts.length
      newwords.push(parts[j])
      newcols.push((j == parts.length - 1) ? textcols[i] : nil)
    end
  end
  return [newwords, newcols]
end

# ---- 来自官方 Essentials 18.1 源码：234028_DrawText.rb ----
def getLineBrokenChunks(bitmap,value,width,dims,plain=false)
  x=0
  y=0
  textheight=0
  ret=[]
  if dims
    dims[0]=0
    dims[1]=0
  end
  re=/<c=([^>]+)>/
  reNoMatch=/<c=[^>]+>/
  return ret if !bitmap || bitmap.disposed? || width<=0
  textmsg=value.clone
  color=Font.default_color
  while (c = textmsg.slice!(/\n|[^ \r\t\f\n\-]*\-+|(\S*([ \r\t\f]?))/)) != nil
    break if c==""
    ccheck=c
    if ccheck=="\n"
      x=0
#      y+=(textheight==0) ? bitmap.text_size("X").height : textheight
      y+=(textheight==0) ? bitmap.text_size("X").height+1 : textheight
      textheight=0
      next
    end
    if ccheck[/</] && !plain
      textcols=[]
      ccheck.scan(re) { textcols.push(rgbToColor($1)) }
      # ★ 中文补丁：拆开汉字后再把颜色对齐到原词的末字
      words,textcols=_pkmn_split_words(ccheck.split(reNoMatch), textcols)
    else
      textcols=[]
      # ★ 中文补丁：汉字逐字成词（见 _pkmn_words）
      words=_pkmn_words(ccheck)
    end
    for i in 0...words.length
      word=words[i]
      if word && word!=""
        textSize=bitmap.text_size(word)
        textwidth=textSize.width
        # ★ 中文补丁：下一个字是标点就不断行（免得标点跑到行首）
        if x>0 && x+textwidth>width && !_pkmn_line_start_bad?(word)
          minTextSize=bitmap.text_size(word.gsub(/\s*/,""))
          if x>0 && x+minTextSize.width>width
            x=0
#            y+=32 # (textheight==0) ? bitmap.text_size("X").height : textheight
            y+=(textheight==0) ? bitmap.text_size("X").height+1 : textheight
            textheight=0
          end
        end
#        textheight=32 # [textheight,textSize.height].max
        textheight=[textheight,textSize.height+1].max
        ret.push([word,x,y,textwidth,textheight,color])
        x+=textwidth
        dims[0]=x if dims && dims[0]<x
      end
      if textcols[i]
        color=textcols[i]
      end
    end
  end
  dims[1]=y+textheight if dims
  return ret
end

# ---- 来自官方 Essentials 18.1 源码：472422_TextEntry.rb ----
def getLineBrokenText(bitmap,value,width,dims)
  x=0
  y=0
  textheight=0
  ret=[]
  if dims
    dims[0]=0
    dims[1]=0
  end
  line=0
  position=0
  column=0
  return ret if !bitmap || bitmap.disposed? || width<=0
  textmsg=value.clone
  ret.push(["",0,0,0,bitmap.text_size("X").height,0,0,0,0])
  while ((c = textmsg.slice!(/\n|(\S*([ \r\t\f]?))/)) != nil)
    break if c==""
    length=_pkmn_chars(c).length
    ccheck=c
    if ccheck=="\n"
      ret.push(["\n",x,y,0,textheight,line,position,column,0])
      x=0
      y+=(textheight==0) ? bitmap.text_size("X").height : textheight
      line+=1
      textheight=0
      column=0
      position+=length
      ret.push(["",x,y,0,textheight,line,position,column,0])
      next
    end
    # ★ 中文补丁：汉字逐字成词（见 _pkmn_words）
    words=_pkmn_words(ccheck)
    for i in 0...words.length
      word=words[i]
      if word && word!=""
        textSize=bitmap.text_size(word)
        textwidth=textSize.width
        if x>0 && x+textwidth>=width-2
          # Zero-length word break
          ret.push(["",x,y,0,textheight,line,position,column,0])
          x=0
          column=0
          y+=(textheight==0) ? bitmap.text_size("X").height : textheight
          line+=1
          textheight=0
        end
        textheight=[textheight,textSize.height].max
        ret.push([word,x,y,textwidth,textheight,line,position,column,length])
        x+=textwidth
        dims[0]=x if dims && dims[0]<x
      end
    end
    position+=length
    column+=length
  end
  dims[1]=y+textheight if dims
  return ret
end

# ---- 来自官方 Essentials 18.1 源码：234028_DrawText.rb ----
def getFormattedText(bitmap,xDst,yDst,widthDst,heightDst,text,lineheight=32,
                     newlineBreaks=true,explicitBreaksOnly=false,
                     collapseAlignments=false)
  dummybitmap=nil
  if !bitmap || bitmap.disposed?   # allows function to be called with nil bitmap
    dummybitmap=Bitmap.new(1,1)
    bitmap=dummybitmap
    return
  end
  if !bitmap || bitmap.disposed? || widthDst<=0 || heightDst==0 || text.length==0
    return []
  end
  textchunks=[]
  controls=[]
  oldtext=text
  while text[FORMATREGEXP]
    textchunks.push($~.pre_match)
    if $~[3]
      controls.push([$~[2].downcase,$~[4],-1,$~[1]=="/" ? true : false])
    else
      controls.push([$~[2].downcase,"",-1,$~[1]=="/" ? true : false])
    end
    text=$~.post_match
  end
  if controls.length==0
    ret=getFormattedTextFast(bitmap,xDst,yDst,widthDst,heightDst,text,lineheight,
       newlineBreaks,explicitBreaksOnly)
    dummybitmap.dispose if dummybitmap
    return ret
  end
  x=y=0
  characters=[]
  charactersInternal=[]
  realtext=nil
  realtextStart=""
  if !explicitBreaksOnly && textchunks.join("").length==0
    # All commands occurred at the beginning of the text string
    realtext=(newlineBreaks) ? text : text.gsub(/\n/," ")
    realtextStart=oldtext[0,oldtext.length-realtext.length]
    realtextHalf=text.length/2
  end
  textchunks.push(text)
  for chunk in textchunks
    chunk.gsub!(/&lt;/,"<")
    chunk.gsub!(/&gt;/,">")
    chunk.gsub!(/&apos;/,"'")
    chunk.gsub!(/&quot;/,"\"")
    chunk.gsub!(/&amp;/,"&")
  end
  textlen=0
  for i in 0...controls.length
    textlen+=_pkmn_chars(textchunks[i]).length
    controls[i][2]=textlen
  end
  text=textchunks.join("")
  textchars=_pkmn_chars(text)
  colorstack=[]
  boldcount=0
  italiccount=0
  outlinecount=0
  underlinecount=0
  strikecount=0
  rightalign=0
  outline2count=0
  opacitystack=[]
  oldfont=bitmap.font.clone
  defaultfontname=bitmap.font.name
  defaultfontsize=bitmap.font.size
  fontsize=defaultfontsize
  fontnamestack=[]
  fontsizestack=[]
  defaultcolors=[oldfont.color.clone,nil]
  if defaultfontname.is_a?(Array)
    defaultfontname=defaultfontname.find { |i| Font.exist?(i) } || "Arial"
  elsif !Font.exist?(defaultfontname)
    defaultfontname="Arial"
  end
  defaultfontname=defaultfontname.clone
  fontname=defaultfontname
  alignstack=[]
  lastword=[0,0] # position of last word
  hadspace=false
  hadnonspace=false
  havenl=false
  position=0
  while position<textchars.length
    nextline=0
    graphic=nil
    graphicX=0
    graphicY=0
    graphicWidth=nil
    graphicHeight=nil
    graphicRect=nil
    for i in 0...controls.length
      if controls[i] && controls[i][2]==position
        control=controls[i][0]
        param=controls[i][1]
        endtag=controls[i][3]
        if control=="c"
          if endtag
            colorstack.pop
          else
            color=rgbToColor(param)
            colorstack.push([color,nil])
          end
        elsif control=="c2"
          if endtag
            colorstack.pop
          else
            base=Rgb16ToColor(param[0,4])
            shadow=Rgb16ToColor(param[4,4])
            colorstack.push([base,shadow])
          end
        elsif control=="c3"
          if endtag
            colorstack.pop
          else
            param=param.split(",")
            # get pure colors unaffected by opacity
            oldColors=getLastParam(colorstack,defaultcolors)
            base=(param[0] && param[0]!="") ? rgbToColor(param[0]) : oldColors[0]
            shadow=(param[1] && param[1]!="") ? rgbToColor(param[1]) : oldColors[1]
            colorstack.push([base,shadow])
          end
        elsif control=="o"
          if endtag
            opacitystack.pop
          else
            opacitystack.push(param.sub(/\s+$/,"").to_i)
          end
        elsif control=="b"
          boldcount+=(endtag ? -1 : 1)
        elsif control=="i"
          italiccount+=(endtag ? -1 : 1)
        elsif control=="u"
          underlinecount+=(endtag ? -1 : 1)
        elsif control=="s"
          strikecount+=(endtag ? -1 : 1)
        elsif control=="outln"
          outlinecount+=(endtag ? -1 : 1)
        elsif control=="outln2"
          outline2count+=(endtag ? -1 : 1)
        elsif control=="fs" # Font size
          if endtag
            fontsizestack.pop
          else
            fontsizestack.push(param.sub(/\s+$/,"").to_i)
          end
          fontsize=getLastParam(fontsizestack,defaultfontsize)
          bitmap.font.size=fontsize
        elsif control=="fn" # Font name
          if endtag
            fontnamestack.pop
          else
            fontname=param.sub(/\s+$/,"")
            fontnamestack.push(Font.exist?(fontname) ? fontname : "Arial")
          end
          fontname=getLastParam(fontnamestack,defaultfontname)
          bitmap.font.name=fontname
        elsif control=="ar" # Right align
          if !endtag
            alignstack.push(1)
            nextline=1 if x>0 && nextline==0
          else
            alignstack.pop
            nextline=1 if x>0 && nextline==0
          end
        elsif control=="al" # Left align
          if !endtag
            alignstack.push(0)
            nextline=1 if x>0 && nextline==0
          else
            alignstack.pop;
            nextline=1 if x>0 && nextline==0
          end
        elsif control=="ac" # Center align
          if !endtag
            alignstack.push(2)
            nextline=1 if x>0 && nextline==0
          else
            alignstack.pop;
            nextline=1 if x>0 && nextline==0
          end
        elsif control=="icon" # Icon
          if !endtag
            param=param.sub(/\s+$/,"")
            graphic="Graphics/Icons/#{param}"
            controls[i]=nil
            break
          end
        elsif control=="img" # Icon
          if !endtag
            param=param.sub(/\s+$/,"")
            param=param.split("|")
            graphic=param[0]
            if param.length>1
              graphicX=param[1].to_i
              graphicY=param[2].to_i
              graphicWidth=param[3].to_i
              graphicHeight=param[4].to_i
            end
            controls[i]=nil
            break
          end
        elsif control=="br" # Line break
          if !endtag
            nextline+=1
          end
        elsif control=="r" # Right align this line
          if !endtag
            x=0
            rightalign=1; lastword=[characters.length,x]
          end
        end
        controls[i]=nil
      end
    end
    bitmap.font.bold=(boldcount>0)
    bitmap.font.italic=(italiccount>0)
    if graphic
      if !graphicWidth
        tempgraphic=Bitmap.new(graphic)
        graphicWidth=tempgraphic.width
        graphicHeight=tempgraphic.height
        tempgraphic.dispose
      end
      width=graphicWidth   # +8  # No padding
      xStart=0   # 4
      yStart=[(lineheight/2)-(graphicHeight/2),0].max
      graphicRect=Rect.new(graphicX,graphicY,graphicWidth,graphicHeight)
    else
      yStart=0
      xStart=0
      width=isWaitChar(textchars[position]) ? 0 : bitmap.text_size(textchars[position]).width
      width+=2 if width>0 && outline2count>0
    end
    if rightalign==1 && nextline==0
      alignment=1
    else
      alignment=getLastParam(alignstack,0)
    end
    nextline.times do
      havenl=true
      characters.push(["\n",x,y*lineheight+yDst,0,lineheight,false,false,false,
         defaultcolors[0],defaultcolors[1],false,false,"",8,position,nil,0])
      charactersInternal.push([alignment,y,0])
      y+=1;
      x=0;
      rightalign=0;
      lastword=[characters.length,x]
      hadspace=false
      hadnonspace=false
    end
    if textchars[position]=="\n"
      if newlineBreaks
        if nextline==0
          havenl=true
          characters.push(["\n",x,y*lineheight+yDst,0,lineheight,false,false,false,
             defaultcolors[0],defaultcolors[1],false,false,"",8,position,nil,0])
          charactersInternal.push([alignment,y,0])
          y+=1
          x=0
        end
        rightalign=0
        hadspace=true
        hadnonspace=false
        position+=1
        next
      else
        textchars[position]=" "
        if !graphic
          width=bitmap.text_size(textchars[position]).width
          width+=2 if width>0 && outline2count>0
        end
      end
    end
    # ★ 中文换行补丁：原版只在「空格后的词首」记断点，中文没空格 → 永不换行。
    #   这里让汉字逐字可断，非汉字仍走原来的空格逻辑。
    if !ischinese?(textchars[position])
      isspace=(textchars[position][/\s/] || isWaitChar(textchars[position])) ? true : false
      if hadspace && !isspace
        # set last word to here
        lastword[0]=characters.length
        lastword[1]=x
        hadspace=false
        hadnonspace=true
      elsif isspace
        hadspace=true
      end
    else
      lastword[0] = characters.length
      lastword[1] = x
    end
    texty=(lineheight*y)+yDst+yStart
    colors=getLastColors(colorstack,opacitystack,defaultcolors)
    # Push character
    if heightDst<0 || texty<yDst+heightDst
      havenl=true if !graphic && isWaitChar(textchars[position])
      extraspace=(!graphic && italiccount>0) ? 2+(width/2) : 2
      characters.push([
         graphic ? graphic : textchars[position],
         x+xStart,texty,width+extraspace,lineheight,
         graphic ? true : false,
         (boldcount>0),(italiccount>0),colors[0],colors[1],
         (underlinecount>0),(strikecount>0),fontname,fontsize,
         position,graphicRect,
         ((outlinecount>0) ? 1 : 0)+((outline2count>0) ? 2 : 0)
      ])
      charactersInternal.push([alignment,y,xStart,textchars[position],extraspace])
    end
    x+=width
    if !explicitBreaksOnly && x+2>widthDst && lastword[1]!=0 &&
       (!hadnonspace || !hadspace)
      havenl=true
      characters.insert(lastword[0],["\n",x,y*lineheight+yDst,0,lineheight,false,
         false,false,defaultcolors[0],defaultcolors[1],false,false,"",8,position,
         nil])
      charactersInternal.insert(lastword[0],[alignment,y,0])
      lastword[0]+=1
      y+=1
      x=0
      for i in lastword[0]...characters.length
        characters[i][2]+=lineheight
        charactersInternal[i][1]+=1
        extraspace=(charactersInternal[i][4]) ? charactersInternal[i][4] : 0
        charwidth=characters[i][3]-extraspace
        characters[i][1]=x+charactersInternal[i][2]
        x+=charwidth
      end
      lastword[1]=0
    end
    position+=1 if !graphic
  end
  # This code looks at whether the text occupies exactly two lines when
  # displayed. If it does, it balances the length of each line.
=begin
  # Count total number of lines
  numlines = (x==0 && y>0) ? y : y+1
  if numlines==2 && realtext && !realtext[/\n/] && realtext.length>=50
    # Set half to middle of text (known to contain no formatting)
    half = realtext.length/2
    leftSearch  = 0
    rightSearch = 0
    # Search left for a space
    i = half; while i>=0
      break if realtext[i,1][/\s/]||isWaitChar(realtext[i,1])   # found a space
      leftSearch += 1
      i -= 1
    end
    # Search right for a space
    i = half; while i<realtext.length
      break if realtext[i,1][/\s/]||isWaitChar(realtext[i,1])   # found a space
      rightSearch += 1
      i += 1
    end
    # Move half left or right whichever is closer
    trialHalf = half+((rightSearch<leftSearch) ? rightSearch : -leftSearch)
    if trialHalf!=0 && trialHalf!=realtext.length
      # Insert newline and re-call this function (force newlineBreaksOnly)
      newText = realtext.clone
      if isWaitChar(newText[trialHalf,1])
        # insert after wait character
        newText.insert(trialHalf+1,"\n")
      else
        # remove spaces after newline
        newText.insert(trialHalf,"\n")
        newText.gsub!(/\n\s+/,"\n")
      end
      bitmap.font = oldfont
      dummybitmap.dispose if dummybitmap
      return getFormattedText(dummybitmap ? nil : bitmap,xDst,yDst,
         widthDst,heightDst,realtextStart+newText,
         lineheight,true,explicitBreaksOnly)
    end
  end
=end
  if havenl
    # Eliminate spaces before newlines and pause character
    firstspace=-1
    for i in 0...characters.length
      if characters[i][5]!=false # If not a character
        firstspace=-1
      elsif (characters[i][0]=="\n" || isWaitChar(characters[i][0])) &&
         firstspace>=0
        for j in firstspace...i
          characters[j]=nil
          charactersInternal[j]=nil
        end
        firstspace=-1
      elsif characters[i][0][/[ \r\t]/]
        if firstspace<0
          firstspace=i
        end
      else
        firstspace=-1
      end
    end
    if firstspace>0
      for j in firstspace...characters.length
        characters[j]=nil
        charactersInternal[j]=nil
      end
    end
    characters.compact!
    charactersInternal.compact!
  end
  # Calculate Xs based on alignment
  # First, find all text runs with the same alignment on the same line
  totalwidth=0
  widthblocks=[]
  lastalign=0
  lasty=0
  runstart=0
  for i in 0...characters.length
    c=characters[i]
    if i>0 && (charactersInternal[i][0]!=lastalign ||
       charactersInternal[i][1]!=lasty)
      # Found end of run
      widthblocks.push([runstart,i,lastalign,totalwidth,lasty])
      runstart=i
      totalwidth=0
    end
    lastalign=charactersInternal[i][0]
    lasty=charactersInternal[i][1]
    extraspace=(charactersInternal[i][4]) ? charactersInternal[i][4] : 0
    totalwidth+=c[3]-extraspace
  end
  widthblocks.push([runstart,characters.length,lastalign,totalwidth,lasty])
  if collapseAlignments
    # Calculate the total width of each line
    totalLineWidths=[]
    for block in widthblocks
      y=block[4]
      if !totalLineWidths[y]
        totalLineWidths[y]=0
      end
      if totalLineWidths[y]!=0
        # padding in case more than one line has different alignments
        totalLineWidths[y]+=16
      end
      totalLineWidths[y]+=block[3]
    end
    # Calculate a new width for the next step
    widthDst=[widthDst,(totalLineWidths.compact.max || 0)].min
  end
  # Now, based on the text runs found, recalculate Xs
  for block in widthblocks
    next if block[0]>=block[1]
    for i in block[0]...block[1]
      case block[2]
      when 1; characters[i][1]=xDst+(widthDst-block[3]-4)+characters[i][1]
      when 2; characters[i][1]=xDst+((widthDst/2)-(block[3]/2))+characters[i][1]
      else; characters[i][1]=xDst+characters[i][1]
      end
    end
  end
  # Remove all characters with Y greater or equal to _yDst_+_heightDst_
  if heightDst>=0
    for i in 0...characters.length
      if characters[i][2]>=yDst+heightDst
        characters[i]=nil
      end
    end
    characters.compact!
  end
  bitmap.font=oldfont
  dummybitmap.dispose if dummybitmap
  return characters
end

# ---- 来自官方 Essentials 18.1 源码：234028_DrawText.rb ----
def getFormattedTextFast(bitmap,xDst,yDst,widthDst,heightDst,text,lineheight,
                         newlineBreaks=true,explicitBreaksOnly=false)
  x=y=0
  characters=[]
  textchunks=[]
  textchunks.push(text)
  text=textchunks.join("")
  textchars=_pkmn_chars(text)
  lastword=[0,0] # position of last word
  hadspace=false
  hadnonspace=false
  bold=bitmap.font.bold
  italic=bitmap.font.italic
  colorclone=bitmap.font.color
  defaultfontname=bitmap.font.name
  if defaultfontname.is_a?(Array)
    defaultfontname=defaultfontname.find { |i| Font.exist?(i) } || "Arial"
  elsif !Font.exist?(defaultfontname)
    defaultfontname="Arial"
  end
  defaultfontname=defaultfontname.clone
  havenl=false
  position=0
  while position<textchars.length
    yStart=0
    xStart=0
    width=isWaitChar(textchars[position]) ? 0 : bitmap.text_size(textchars[position]).width
    if textchars[position]=="\n"
      if newlineBreaks   # treat newline as break
        havenl=true
        characters.push(["\n",x,y*lineheight+yDst,0,lineheight,false,false,
           false,colorclone,nil,false,false,"",8,position,nil,0])
        y+=1
        x=0
        hadspace=true
        hadnonspace=false
        position+=1
        next
      else   # treat newline as space
        textchars[position]=" "
      end
    end
    # ★ 中文换行补丁：原版只在「空格后的词首」记断点，中文没空格 → 永不换行。
    #   这里让汉字逐字可断，非汉字仍走原来的空格逻辑。
    if !ischinese?(textchars[position])
      isspace=(textchars[position][/\s/]||isWaitChar(textchars[position]))  ? true : false
      if hadspace && !isspace
        # set last word to here
        lastword[0]=characters.length
        lastword[1]=x
        hadspace=false
        hadnonspace=true
      elsif isspace
        hadspace=true
      end
    else
      lastword[0] = characters.length
      lastword[1] = x
    end
    texty=(lineheight*y)+yDst+yStart
    # Push character
    if heightDst<0 || yStart<yDst+heightDst
      havenl=true if isWaitChar(textchars[position])
      characters.push([
         textchars[position],
         x+xStart,texty+yStart,width+2,lineheight,
         false,bold,italic,colorclone,nil,false,false,
         defaultfontname,bitmap.font.size,position,nil,0])
    end
    x+=width
    if !explicitBreaksOnly && x+2>widthDst && lastword[1]!=0 &&
       (!hadnonspace || !hadspace)
      havenl=true
      characters.insert(lastword[0],["\n",x,y*lineheight+yDst,0,lineheight,
         false,false,false,colorclone,nil,false,false,"",8,position])
      lastword[0]+=1
      y+=1
      x=0
      for i in lastword[0]...characters.length
        characters[i][2]+=lineheight
        charwidth=characters[i][3]-2
        characters[i][1]=x
        x+=charwidth
      end
      lastword[1]=0
    end
    position+=1
  end
  # This code looks at whether the text occupies exactly two lines when
  # displayed. If it does, it balances the length of each line.
=begin
  # Count total number of lines
  numlines = (x==0 && y>0) ? y-1 : y
  realtext = (newlineBreaks) ? text : text.gsub(/\n/," ")
  if numlines==2 && !explicitBreaksOnly && !realtext[/\n/] && realtext.length>=50
    # Set half to middle of text (known to contain no formatting)
    half = realtext.length/2
    leftSearch  = 0
    rightSearch = 0
    # Search left for a space
    i = half; while i>=0
      break if realtext[i,1][/\s/]||isWaitChar(realtext[i])   # found a space
      leftSearch += 1
      i -= 1
    end
    # Search right for a space
    i = half; while i<realtext.length
      break if realtext[i,1][/\s/]||isWaitChar(realtext[i])   # found a space
      rightSearch += 1
      i += 1
    end
    # Move half left or right whichever is closer
    trialHalf = half+((leftSearch<rightSearch) ? -leftSearch : rightSearch)
    if trialHalf!=0 && trialHalf!=realtext.length
      # Insert newline and re-call this function (force explicitBreaksOnly)
      newText = realtext.clone
      newText.insert(trialHalf,"\n")
      return getFormattedTextFast(bitmap,xDst,yDst,
         widthDst,heightDst,newText,lineheight,true,explicitBreaksOnly)
    end
  end
=end
  # Eliminate spaces before newlines and pause character
  if havenl
    firstspace=-1
    for i in 0...characters.length
      if characters[i][5]!=false # If not a character
        firstspace=-1
      elsif (characters[i][0]=="\n" || isWaitChar(characters[i][0])) &&
         firstspace>=0
        for j in firstspace...i
          characters[j]=nil
        end
        firstspace=-1
      elsif characters[i][0][/[ \r\t]/]
        if firstspace<0
          firstspace=i
        end
      else
        firstspace=-1
      end
    end
    if firstspace>0
      for j in firstspace...characters.length
        characters[j]=nil
      end
    end
    characters.compact!
  end
  for i in 0...characters.length
    characters[i][1]=xDst+characters[i][1]
  end
  # Remove all characters with Y greater or equal to _yDst_+_heightDst_
  if heightDst>=0
    for i in 0...characters.length
      if characters[i][2]>=yDst+heightDst
        characters[i]=nil
      end
    end
    characters.compact!
  end
  return characters
end

# ---- 来自官方 Essentials 18.1 源码：234028_DrawText.rb ----
def pbDrawShadowText(bitmap,x,y,width,height,string,baseColor,shadowColor=nil,align=0)
  return if !bitmap || !string
  width=(width<0) ? bitmap.text_size(string).width+4 : width
  height=(height<0) ? bitmap.text_size(string).height+4 : height
  # ★ 中文文本处理：整体垂直偏移（值在同目录 Settings.rb 里调）
  y = y + Settings::Y_OFFSET_OF_TEXT - Settings::Y_OFFSET_OF_ORDER_CORRCETION
  if shadowColor && shadowColor.alpha>0
    bitmap.font.color=shadowColor
    bitmap.draw_text(x+2,y,width,height,string,align)
    bitmap.draw_text(x,y+2,width,height,string,align)
    bitmap.draw_text(x+2,y+2,width,height,string,align)
  end
  if baseColor && baseColor.alpha>0
    bitmap.font.color=baseColor
    bitmap.draw_text(x,y,width,height,string,align)
  end
end
