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
  char.ord >= 0x4e00 && char.ord <= 0x9fa5
end

def _MAPINTL(mapid, *arg)
  string = MessageTypes.getFromMapHash(mapid, arg[0])
  string = string.clone
  (1...arg.length).each do |i|
    string.gsub!(/\{#{i}\}/, arg[i].to_s) 
  end
  string = string.gsub(/([\p{Han}\p{P}])\s+([\p{Han}\p{P}])/, '\1\2')
  return string
end

def getFormattedText(bitmap, xDst, yDst, widthDst, heightDst, text, lineheight = 32,
                     newlineBreaks = true, explicitBreaksOnly = false,
                     collapseAlignments = false)
  dummybitmap = nil
  if !bitmap || bitmap.disposed?   # allows function to be called with nil bitmap
    dummybitmap = Bitmap.new(1, 1)
    bitmap = dummybitmap
    return
  end
  if !bitmap || bitmap.disposed? || widthDst <= 0 || heightDst == 0 || text.length == 0
    return []
  end
  textchunks = []
  controls = []
  #  oldtext = text
  while text[FORMATREGEXP]
    textchunks.push($~.pre_match)
    if $~[3]
      controls.push([$~[2].downcase, $~[4], -1, $~[1] == "/"])
    else
      controls.push([$~[2].downcase, "", -1, $~[1] == "/"])
    end
    text = $~.post_match
  end
  if controls.length == 0
    ret = getFormattedTextFast(bitmap, xDst, yDst, widthDst, heightDst, text, lineheight,
                               newlineBreaks, explicitBreaksOnly)
    dummybitmap&.dispose
    return ret
  end
  x = y = 0
  characters = []
  charactersInternal = []
  textchunks.push(text)
  textchunks.each { |chunk| fmtReplaceEscapes(chunk) }
  textlen = 0
  controls.each_with_index do |control, i|
    textlen += textchunks[i].scan(/./m).length
    control[2] = textlen
  end
  text = textchunks.join
  textchars = text.scan(/./m)
  colorstack = []
  boldcount = 0
  italiccount = 0
  outlinecount = 0
  underlinecount = 0
  strikecount = 0
  rightalign = 0
  outline2count = 0
  opacitystack = []
  oldfont = bitmap.font.clone
  defaultfontname = bitmap.font.name
  defaultfontsize = bitmap.font.size
  fontsize = defaultfontsize
  fontnamestack = []
  fontsizestack = []
  defaultcolors = [oldfont.color.clone, nil]
  if defaultfontname.is_a?(Array)
    defaultfontname = defaultfontname.find { |i| Font.exist?(i) } || "Arial"
  elsif !Font.exist?(defaultfontname)
    defaultfontname = "Arial"
  end
  defaultfontname = defaultfontname.clone
  fontname = defaultfontname
  alignstack = []
  lastword = [0, 0] # position of last word
  hadspace = false
  hadnonspace = false
  havenl = false
  position = 0
  while position < textchars.length
    nextline = 0
    graphic = nil
    graphicX = 0
    graphicY = 4
    graphicWidth = nil
    graphicHeight = nil
    graphicRect = nil
    controls.length.times do |i|
      next if !controls[i] || controls[i][2] != position
      control = controls[i][0]
      param = controls[i][1]
      endtag = controls[i][3]
      case control
      when "c" then endtag ? colorstack.pop : colorstack.push([Color.new_from_rgb(param), nil])
      when "c2" then endtag ? colorstack.pop : colorstack.push([Color.new_from_rgb(param[0, 4]), Color.new_from_rgb(param[4, 4])])
      when "c3"
        if endtag
          colorstack.pop
        else
          param = param.split(",")
          oldColors = getLastParam(colorstack, defaultcolors)
          base = param[0].empty? ? oldColors[0] : Color.new_from_rgb(param[0])
          shadow = param[1].empty? ? oldColors[1] : Color.new_from_rgb(param[1])
          colorstack.push([base, shadow])
        end
      when "o" then endtag ? opacitystack.pop : opacitystack.push(param.sub(/\s+$/, "").to_i)
      when "b" then boldcount += endtag ? -1 : 1
      when "i" then italiccount += endtag ? -1 : 1
      when "u" then underlinecount += endtag ? -1 : 1
      when "s" then strikecount += endtag ? -1 : 1
      when "outln" then outlinecount += endtag ? -1 : 1
      when "outln2" then outline2count += endtag ? -1 : 1
      when "fs" then endtag ? fontsizestack.pop : fontsizestack.push(param.sub(/\s+$/, "").to_i)
      when "fn" then endtag ? fontnamestack.pop : fontnamestack.push(Font.exist?(param.sub(/\s+$/, "")) ? param.sub(/\s+$/, "") : "Arial")
      when "ar", "al", "ac" 
        endtag ? alignstack.pop : alignstack.push(control[0] == "ar" ? 1 : control[0] == "al" ? 0 : 2)
        nextline = 1 if x > 0 && nextline == 0
      when "icon" then graphic = "Graphics/Icons/#{param.sub(/\s+$/, "")}" unless endtag
      when "img"
        unless endtag
          param = param.sub(/\s+$/, "").split("|")
          graphic = param[0]
          if param.length > 1
            graphicX, graphicY, graphicWidth, graphicHeight = param[1..4].map(&:to_i)
          end
        end
      when "br" then nextline += 1 unless endtag
      when "r"
        unless endtag
          x = 0
          rightalign = 1
          lastword = [characters.length, x]
        end
      end
      controls[i] = nil
    end
    bitmap.font.bold = (boldcount > 0)
    bitmap.font.italic = (italiccount > 0)
    if graphic
      if !graphicWidth
        tempgraphic = Bitmap.new(graphic)
        graphicWidth = tempgraphic.width
        graphicHeight = tempgraphic.height
        tempgraphic.dispose
      end
      width = graphicWidth   # +8  # No padding
      xStart = 0   # 4
      yStart = [(lineheight / 2) - (graphicHeight / 2), 0].max
      yStart += 4   # TEXT OFFSET
      graphicRect = Rect.new(graphicX, graphicY, graphicWidth, graphicHeight)
    else
      xStart = 0
      yStart = 0
      width = isWaitChar(textchars[position]) ? 0 : bitmap.text_size(textchars[position]).width
      width += 2 if width > 0 && outline2count > 0
    end
    if rightalign == 1 && nextline == 0
      alignment = 1
    else
      alignment = getLastParam(alignstack, 0)
    end
    nextline.times do
      havenl = true
      characters.push(["\n", x, (y * lineheight) + yDst, 0, lineheight, false, false, false,
                       defaultcolors[0], defaultcolors[1], false, false, "", 8, position, nil, 0])
      charactersInternal.push([alignment, y, 0])
      y += 1
      x = 0
      rightalign = 0
      lastword = [characters.length, x]
      hadspace = false
      hadnonspace = false
    end
    if textchars[position] == "\n"
      if newlineBreaks
        if nextline == 0
          havenl = true
          characters.push(["\n", x, (y * lineheight) + yDst, 0, lineheight, false, false, false,
                           defaultcolors[0], defaultcolors[1], false, false, "", 8, position, nil, 0])
          charactersInternal.push([alignment, y, 0])
          y += 1
          x = 0
        end
        rightalign = 0
        hadspace = true
        hadnonspace = false
        position += 1
        next
      else
        textchars[position] = " "
        if !graphic
          width = bitmap.text_size(textchars[position]).width
          width += 2 if width > 0 && outline2count > 0
        end
      end
    end
    if !ischinese?(textchars[position])
      isspace = (textchars[position][/\s/] || isWaitChar(textchars[position])) ? true : false
      if hadspace && !isspace
        # set last word to here
        lastword[0] = characters.length
        lastword[1] = x
        hadspace = false
        hadnonspace = true
      elsif isspace
        hadspace = true
      end
    else
      lastword[0] = characters.length
      lastword[1] = x
    end
    texty = (lineheight * y) + yDst + yStart - 2   # TEXT OFFSET
    colors = getLastColors(colorstack, opacitystack, defaultcolors)
    # Push character
    if heightDst < 0 || texty < yDst + heightDst
      havenl = true if !graphic && isWaitChar(textchars[position])
      extraspace = (!graphic && italiccount > 0) ? 2 + (width / 2) : 2
      characters.push([graphic || textchars[position],
                       x + xStart, texty, width + extraspace, lineheight,
                       graphic ? true : false,
                       (boldcount > 0), (italiccount > 0), colors[0], colors[1],
                       (underlinecount > 0), (strikecount > 0), fontname, fontsize,
                       position, graphicRect,
                       ((outlinecount > 0) ? 1 : 0) + ((outline2count > 0) ? 2 : 0)])
      charactersInternal.push([alignment, y, xStart, textchars[position], extraspace])
    end
    x += width
    if !explicitBreaksOnly && x + 2 > widthDst && lastword[1] != 0 &&
       (!hadnonspace || !hadspace)
      havenl = true
      characters.insert(lastword[0], ["\n", x, (y * lineheight) + yDst, 0, lineheight,
                                      false, false, false,
                                      defaultcolors[0], defaultcolors[1],
                                      false, false, "", 8, position, nil])
      charactersInternal.insert(lastword[0], [alignment, y, 0])
      lastword[0] += 1
      y += 1
      x = 0
      (lastword[0]...characters.length).each do |i|
        characters[i][2] += lineheight
        charactersInternal[i][1] += 1
        extraspace = (charactersInternal[i][4]) ? charactersInternal[i][4] : 0
        charwidth = characters[i][3] - extraspace
        characters[i][1] = x + charactersInternal[i][2]
        x += charwidth
      end
      lastword[1] = 0
    end
    position += 1 if !graphic
  end
  # This code looks at whether the text occupies exactly two lines when
  # displayed. If it does, it balances the length of each line.
  if havenl
    # Eliminate spaces before newlines and pause character
    firstspace = -1
    characters.length.times do |i|
      if characters[i][5] != false # If not a character
        firstspace = -1
      elsif (characters[i][0] == "\n" || isWaitChar(characters[i][0])) &&
            firstspace >= 0
        (firstspace...i).each do |j|
          characters[j] = nil
          charactersInternal[j] = nil
        end
        firstspace = -1
      elsif characters[i][0][/[ \r\t]/]
        firstspace = i if firstspace < 0
      else
        firstspace = -1
      end
    end
    if firstspace > 0
      (firstspace...characters.length).each do |j|
        characters[j] = nil
        charactersInternal[j] = nil
      end
    end
    characters.compact!
    charactersInternal.compact!
  end
  # Calculate Xs based on alignment
  # First, find all text runs with the same alignment on the same line
  totalwidth = 0
  widthblocks = []
  lastalign = 0
  lasty = 0
  runstart = 0
  characters.length.times do |i|
    c = characters[i]
    if i > 0 && (charactersInternal[i][0] != lastalign ||
       charactersInternal[i][1] != lasty)
      # Found end of run
      widthblocks.push([runstart, i, lastalign, totalwidth, lasty])
      runstart = i
      totalwidth = 0
    end
    lastalign = charactersInternal[i][0]
    lasty = charactersInternal[i][1]
    extraspace = (charactersInternal[i][4]) ? charactersInternal[i][4] : 0
    totalwidth += c[3] - extraspace
  end
  widthblocks.push([runstart, characters.length, lastalign, totalwidth, lasty])
  if collapseAlignments
    # Calculate the total width of each line
    totalLineWidths = []
    widthblocks.each do |block|
      y = block[4]
      totalLineWidths[y] = 0 if !totalLineWidths[y]
      if totalLineWidths[y] != 0
        # padding in case more than one line has different alignments
        totalLineWidths[y] += 16
      end
      totalLineWidths[y] += block[3]
    end
    # Calculate a new width for the next step
    widthDst = [widthDst, (totalLineWidths.compact.max || 0)].min
  end
  # Now, based on the text runs found, recalculate Xs
  widthblocks.each do |block|
    next if block[0] >= block[1]
    (block[0]...block[1]).each do |i|
      case block[2]
      when 1 then characters[i][1] = xDst + (widthDst - block[3] - 4) + characters[i][1]
      when 2 then characters[i][1] = xDst + ((widthDst / 2) - (block[3] / 2)) + characters[i][1]
      else        characters[i][1] = xDst + characters[i][1]
      end
    end
  end
  # Remove all characters with Y greater or equal to _yDst_+_heightDst_
  characters.delete_if { |ch| ch[2] >= yDst + heightDst } if heightDst >= 0
  bitmap.font = oldfont
  dummybitmap&.dispose
  return characters
end

def getFormattedTextFast(bitmap, xDst, yDst, widthDst, heightDst, text, lineheight,
                         newlineBreaks = true, explicitBreaksOnly = false)
  x = y = 0
  characters = []
  textchunks = []
  textchunks.push(text)
  text = textchunks.join
  textchars = text.scan(/./m)
  lastword = [0, 0] # position of last word
  hadspace = false
  hadnonspace = false
  bold = bitmap.font.bold
  italic = bitmap.font.italic
  colorclone = bitmap.font.color
  defaultfontname = bitmap.font.name
  if defaultfontname.is_a?(Array)
    defaultfontname = defaultfontname.find { |i| Font.exist?(i) } || "Arial"
  elsif !Font.exist?(defaultfontname)
    defaultfontname = "Arial"
  end
  defaultfontname = defaultfontname.clone
  havenl = false
  position = 0
  while position < textchars.length
    yStart = 0
    xStart = 0
    width = isWaitChar(textchars[position]) ? 0 : bitmap.text_size(textchars[position]).width
    if textchars[position] == "\n"
      if newlineBreaks   # treat newline as break
        havenl = true
        characters.push(["\n", x, (y * lineheight) + yDst, 0, lineheight, false, false,
                         false, colorclone, nil, false, false, "", 8, position, nil, 0])
        y += 1
        x = 0
        hadspace = true
        hadnonspace = false
        position += 1
        next
      else   # treat newline as space
        textchars[position] = " "
      end
    end
    if ischinese?(textchars[position])
      isspace = (textchars[position][/\s/] || isWaitChar(textchars[position])) ? true : false
      if hadspace && !isspace
        # set last word to here
        lastword[0] = characters.length
        lastword[1] = x
        hadspace = false
        hadnonspace = true
      elsif isspace
        hadspace = true
      end
    else
      lastword[0] = characters.length
      lastword[1] = x
    end
    texty = (lineheight * y) + yDst + yStart
    # Push character
    if heightDst < 0 || yStart < yDst + heightDst
      havenl = true if isWaitChar(textchars[position])
      characters.push([textchars[position],
                       x + xStart, texty, width + 2, lineheight,
                       false, bold, italic, colorclone, nil, false, false,
                       defaultfontname, bitmap.font.size, position, nil, 0])
    end
    x += width
    if !explicitBreaksOnly && x + 2 > widthDst && lastword[1] != 0 &&
       (!hadnonspace || !hadspace)
      havenl = true
      characters.insert(lastword[0], ["\n", x, (y * lineheight) + yDst, 0, lineheight,
                                      false, false, false, colorclone, nil, false, false, "", 8, position])
      lastword[0] += 1
      y += 1
      x = 0
      (lastword[0]...characters.length).each do |i|
        characters[i][2] += lineheight
        charwidth = characters[i][3] - 2
        characters[i][1] = x
        x += charwidth
      end
      lastword[1] = 0
    end
    position += 1
  end
  # Eliminate spaces before newlines and pause character
  if havenl
    firstspace = -1
    characters.length.times do |i|
      if characters[i][5] != false # If not a character
        firstspace = -1
      elsif (characters[i][0] == "\n" || isWaitChar(characters[i][0])) &&
            firstspace >= 0
        (firstspace...i).each do |j|
          characters[j] = nil
        end
        firstspace = -1
      elsif characters[i][0][/[ \r\t]/]
        firstspace = i if firstspace < 0
      else
        firstspace = -1
      end
    end
    if firstspace > 0
      (firstspace...characters.length).each do |j|
        characters[j] = nil
      end
    end
    characters.compact!
  end
  characters.each { |char| char[1] = xDst + char[1] }
  if heightDst >= 0
    characters.each_with_index do |char, i|
      characters[i] = nil if char[2] >= yDst + heightDst
    end
    characters.compact!
  end
  return characters
end

def pbDrawShadowText(bitmap, x, y, width, height, string, baseColor, shadowColor = nil, align = 0)
  return if !bitmap || !string
  width = (width < 0) ? bitmap.text_size(string).width + 1 : width
  height = (height < 0) ? bitmap.text_size(string).height + 1 : height
  y = y + Settings::Y_OFFSET_OF_TEXT - Settings::Y_OFFSET_OF_ORDER_CORRCETION
  if shadowColor && shadowColor.alpha > 0
    bitmap.font.color = shadowColor
    bitmap.draw_text(x + 2, y, width, height, string, align)
    bitmap.draw_text(x, y + 2, width, height, string, align)
    bitmap.draw_text(x + 2, y + 2, width, height, string, align)
  end
  if baseColor && baseColor.alpha > 0
    bitmap.font.color = baseColor
    bitmap.draw_text(x, y, width, height, string, align)
  end
end