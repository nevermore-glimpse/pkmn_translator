# ==============================================================================
# [pkmn] 中文文本处理 · 旧版（Essentials 19.1 之前 / Ruby 1.8）版
#
#   由「中文文本处理 v21.1」（作者：木亦会枯、楠楠楠小鸟）移植而来，
#   功能一致：中文逐字换行、字体替换、文本垂直偏移、地图文本去多余空格。
#
#   ★ 这一份是给**没有插件系统**的老游戏用的（RPG Maker XP + RGSS，
#     Ruby 1.8.1，例如 Pokemon Void / 宝可梦蛋白石 / 绿铀）：
#     · getFormattedText / getFormattedTextFast / pbDrawShadowText 三个函数
#       照抄目标引擎源码后再打补丁（用的都是本引擎自己的助手函数
#       rgbToColor、Rgb16ToColor），不会调用新版专有 API；
#     · 顶部有 Ruby 1.8 兼容补丁（补 String#ord / String#each_char）；
#     · ischinese? 与 _MAPINTL 做了 1.8 适配（见下面各函数上的注释）。
#
#   ★ 这份脚本没有 Plugins 目录可用，是**直接插进 Scripts.rxdata 的最后一个**
#     （或者解包成 Data/Scripts/ 时放一个排最后的 .rb）。
#
#   ★ 禁止手改本文件 —— 要改插件设置请改同目录的 Settings.rb。
# ==============================================================================

# ------------------------------------------------------------------------------
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

    def each_char
      chars = self.scan(/./m)
      return chars if !block_given?
      chars.each { |c| yield c }
      self
    end
  end
end

def getLineBrokenChunks(bitmap, value, width, dims, plain = false)
  x = 0
  y = 0
  ret = []
  if dims
    dims[0] = 0
    dims[1] = 0
  end
  return ret if !bitmap || bitmap.disposed? || width <= 0
  textmsg = value.clone
  color = Font.default_color
  textmsg.each_char do |ch|
    if ch == "\n"
      x = 0
      y += 32
      next
    end
    textSize = bitmap.text_size(ch)
    textwidth = textSize.width
    if x > 0 && x + textwidth > width && ch !~ /[[:punct:]]/
      x = 0
      y += 32
    end
    ret.push([ch, x, y, textwidth, 32, color])
    x += textwidth
    dims[0] = x if dims && dims[0] < x
  end
  dims[1] = y + 32 if dims
  ret
end

def getLineBrokenText(bitmap, value, width, dims)
  x = 0
  y = 0
  textheight = 0
  ret = []
  if dims
    dims[0] = 0
    dims[1] = 0
  end
  return ret if !bitmap || bitmap.disposed? || width <= 0

  textmsg = value.delete(" ").clone
  ret.push(["", 0, 0, 0, bitmap.text_size("中").height, 0, 0, 0, 0])
  textmsg.each_line do |line|
    length = line.scan(/./m).length
    line.each_char do |char|
      textSize = bitmap.text_size(char)
      textwidth = textSize.width
      if x > 0 && x + textwidth >= width - 2
        ret.push(["", x, y, 0, textheight, 0, 0, 0, 0])
        x = 0
        y += textheight.zero? ? bitmap.text_size("国").height : textheight
        textheight = 0
      end
      textheight = [textheight, textSize.height].max
      ret.push([char, x, y, textwidth, textheight, 0, 0, 0, length])
      x += textwidth
      dims[0] = x if dims && dims[0] < x
    end
    y += textheight if y > 0
  end
  dims[1] = y + textheight if dims
  ret
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


def getFormattedText(bitmap,xDst,yDst,widthDst,heightDst,text,lineheight=32,
                     newlineBreaks=true,explicitBreaksOnly=false,
                     collapseAlignments=false)
  dummybitmap=nil
  if !bitmap || bitmap.disposed? # allows function to be called with nil bitmap
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
  numchars=0
  x=y=0
  characters=[]
  charactersInternal=[]
  charsonline=0
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
    textlen+=textchunks[i].scan(/./m).length
    controls[i][2]=textlen
  end
  text=textchunks.join("")
  textchars=text.scan(/./m)
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
    defaultfontname=defaultfontname.find{|i| Font.exist?(i)} || "Arial"
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
  position=0; while position<textchars.length
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
      width=graphicWidth  # +8  # No padding
      xStart=0  # 4
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
    textx=x+xStart # independent of xDst
    texty=(lineheight*y)+yDst+yStart
    colors=getLastColors(colorstack,opacitystack,defaultcolors)
    oldx=x
    # Push character, textx will be calculated later
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
  # Count total number of lines
  numlines=(x==0 && y>0) ? y : y+1
  if numlines==2 && realtext && !realtext[/\n/] && realtext.length>=50
    # Set half to middle of text (known to contain no formatting)
    half=realtext.length/2
    leftSearch=0
    rightSearch=0
    # Search left for a space
    i=half; while i>=0
      if realtext[i,1][/\s/]||isWaitChar(realtext[i,1])
        # found a space
        break
      end
      leftSearch+=1
      i-=1
    end
      # Search right for a space
      i=half; while i<realtext.length
      if realtext[i,1][/\s/]||isWaitChar(realtext[i,1])
        # found a space
        break
      end
      rightSearch+=1
      i+=1
    end
    # Move half left or right whichever is closer
    trialHalf=half+((rightSearch<leftSearch) ? rightSearch : -leftSearch)
    if trialHalf!=0 && trialHalf!=realtext.length
      # Insert newline and re-call this function (force newlineBreaksOnly)
      newText=realtext.clone
      if isWaitChar(newText[trialHalf,1])
        # insert after wait character
        newText.insert(trialHalf+1,"\n")
      else
        # remove spaces after newline
        newText.insert(trialHalf,"\n")
        newText.gsub!(/\n\s+/,"\n")
      end
      bitmap.font=oldfont
      dummybitmap.dispose if dummybitmap
      return getFormattedText(dummybitmap ? nil : bitmap,xDst,yDst,
         widthDst,heightDst,realtextStart+newText,
         lineheight,true,explicitBreaksOnly)
    end
  end
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

def getFormattedTextFast(bitmap,xDst,yDst,widthDst,heightDst,text,lineheight,
                         newlineBreaks=true,explicitBreaksOnly=false)
  numchars=0
  x=y=0
  characters=[]
  charactersInternal=[]
  textchunks=[]
  controls=[]
  charsonline=0
  textchunks.push(text)
  text=textchunks.join("")
  textchars=text.scan(/./m)
  lastword=[0,0] # position of last word
  hadspace=false
  hadnonspace=false
  bold=bitmap.font.bold
  italic=bitmap.font.italic
  colorclone=bitmap.font.color
  defaultfontname=bitmap.font.name
  if defaultfontname.is_a?(Array)
    defaultfontname=defaultfontname.find{|i| Font.exist?(i)} || "Arial"
  elsif !Font.exist?(defaultfontname)
    defaultfontname="Arial"
  end
  defaultfontname=defaultfontname.clone
  havenl=false
  position=0;while position<textchars.length
    yStart=0
    xStart=0
    width=isWaitChar(textchars[position]) ? 0 : bitmap.text_size(textchars[position]).width
    if textchars[position]=="\n"
      if newlineBreaks # treat newline as break
        if true
          havenl=true
          characters.push(["\n",x,y*lineheight+yDst,0,lineheight,false,false,
             false,colorclone,nil,false,false,"",8,position,nil,0])
          y+=1
          x=0
        end
        hadspace=true
        hadnonspace=false
        position+=1
        next
      else # treat newline as space
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
    textx=x+xStart # independent of xDst
    texty=(lineheight*y)+yDst+yStart
    oldx=x
    # Push character, textx will be calculated later
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
  # Count total number of lines
  numlines=(x==0 && y>0) ? y-1 : y
  realtext=(newlineBreaks) ? text : text.gsub(/\n/," ")
  if numlines==2 && !explicitBreaksOnly && !realtext[/\n/] && realtext.length>=50
    # Set half to middle of text (known to contain no formatting)
    half=realtext.length/2
    leftSearch=0
    rightSearch=0
    # Search left for a space
    i=half; while i>=0
      if realtext[i,1][/\s/]||isWaitChar(realtext[i])
        # found a space
        break
      end
      leftSearch+=1
      i-=1
    end
    # Search right for a space
    i=half; while i<realtext.length
      if realtext[i,1][/\s/]||isWaitChar(realtext[i])
        # found a space
        break
      end
      rightSearch+=1
      i+=1
    end
    # Move half left or right whichever is closer
    trialHalf=half+((leftSearch<rightSearch) ? -leftSearch : rightSearch)
    if trialHalf!=0 && trialHalf!=realtext.length
      # Insert newline and re-call this function (force explicitBreaksOnly)
      newText=realtext.clone
      newText.insert(trialHalf,"\n")
      return getFormattedTextFast(bitmap,xDst,yDst,
         widthDst,heightDst,newText,lineheight,true,explicitBreaksOnly)
    end
  end
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

def pbDrawShadowText(bitmap,x,y,width,height,string,baseColor,shadowColor=nil,align=0)
  return if !bitmap || !string
  width=(width<0) ? bitmap.text_size(string).width+4 : width
  height=(height<0) ? bitmap.text_size(string).height+4 : height
  # ★ 中文文本处理：整体垂直偏移（值在插件 Settings.rb 里调）
  y = y + Settings::Y_OFFSET_OF_TEXT - Settings::Y_OFFSET_OF_ORDER_CORRCETION
  if shadowColor
    bitmap.font.color=shadowColor
    bitmap.draw_text(x+2,y,width,height,string,align)
    bitmap.draw_text(x,y+2,width,height,string,align)
    bitmap.draw_text(x+2,y+2,width,height,string,align)
  end
  if baseColor
    bitmap.font.color=baseColor
    bitmap.draw_text(x,y,width,height,string,align)
  end
end
