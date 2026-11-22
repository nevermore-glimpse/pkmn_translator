class PokeSelectionPlaceholderSprite < SpriteWrapper
  attr_accessor :text

  def initialize(pokemon,index,viewport=nil)
    super(viewport)
    xvalues=[0,256,0,256,0,256]
    yvalues=[0,16,96,112,192,208]
    @pbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelBlank")
    self.bitmap=@pbitmap.bitmap
    self.x=xvalues[index]
    self.y=yvalues[index]
    @text=nil
  end

  def update
    super
    @pbitmap.update
    self.bitmap=@pbitmap.bitmap
  end

  def selected
    return false
  end

  def selected=(value)
  end

  def preselected
    return false
  end

  def preselected=(value)
  end

  def switching
    return false
  end

  def switching=(value)
  end

  def refresh
  end

  def dispose
    @pbitmap.dispose
    super
  end
end



class PokeSelectionConfirmCancelSprite < SpriteWrapper
  attr_reader :selected

  def initialize(text,x,y,narrowbox=false,viewport=nil)
    super(viewport)
    @refreshBitmap=true
    @bgsprite=ChangelingSprite.new(0,0,viewport)
    if narrowbox
      @bgsprite.addBitmap("deselbitmap","Graphics/Pictures/partyCancelNarrow")
      @bgsprite.addBitmap("selbitmap","Graphics/Pictures/partyCancelSelNarrow")
    else
      @bgsprite.addBitmap("deselbitmap","Graphics/Pictures/partyCancel")
      @bgsprite.addBitmap("selbitmap","Graphics/Pictures/partyCancelSel")
    end
    @bgsprite.changeBitmap("deselbitmap")
    @overlaysprite=BitmapSprite.new(@bgsprite.bitmap.width,@bgsprite.bitmap.height,viewport)
    @yoffset=8
    ynarrow=narrowbox ? -6 : 0
    pbSetSystemFont(@overlaysprite.bitmap)
    textpos=[[text,56,8+ynarrow,2,Color.new(248,248,248),Color.new(40,40,40)]]
    pbDrawTextPositions(@overlaysprite.bitmap,textpos)
    @overlaysprite.z=self.z+1 # For compatibility with RGSS2
    self.x=x
    self.y=y
  end

  def dispose
    @overlaysprite.bitmap.dispose
    @overlaysprite.dispose
    @bgsprite.dispose
    super
  end

  def viewport=(value)
    super
    refresh
  end

  def color=(value)
    super
    refresh
  end

  def x=(value)
    super
    refresh
  end

  def y=(value)
    super
    refresh
  end

  def selected=(value)
    @selected=value
    refresh
  end

  def refresh
    @bgsprite.changeBitmap((@selected) ? "selbitmap" : "deselbitmap")
    if @bgsprite && !@bgsprite.disposed?
      @bgsprite.x=self.x
      @bgsprite.y=self.y
      @overlaysprite.x=self.x
      @overlaysprite.y=self.y
      @bgsprite.color=self.color
      @overlaysprite.color=self.color
    end
  end
end



class PokeSelectionCancelSprite < PokeSelectionConfirmCancelSprite
  def initialize(viewport=nil)
    super(_INTL("取消"),398,328,false,viewport)
  end
end



class PokeSelectionConfirmSprite < PokeSelectionConfirmCancelSprite
  def initialize(viewport=nil)
    super(_INTL("确认"),398,308,true,viewport)
  end
end



class PokeSelectionCancelSprite2 < PokeSelectionConfirmCancelSprite
  def initialize(viewport=nil)
    super(_INTL("取消"),398,346,true,viewport)
  end
end



class ChangelingSprite < SpriteWrapper
  def initialize(x=0,y=0,viewport=nil)
    super(viewport)
    self.x=x
    self.y=y
    @bitmaps={}
    @currentBitmap=nil
  end

  def addBitmap(key,path)
    if @bitmaps[key]
      @bitmaps[key].dispose
    end
    @bitmaps[key]=AnimatedBitmap.new(path)
  end

  def changeBitmap(key)
    @currentBitmap=@bitmaps[key]
    self.bitmap=@currentBitmap ? @currentBitmap.bitmap : nil
  end

  def dispose
    return if disposed?
    for bm in @bitmaps.values; bm.dispose; end
    @bitmaps.clear
    super
  end

  def update
    return if disposed?
    for bm in @bitmaps.values; bm.update; end
    self.bitmap=@currentBitmap ? @currentBitmap.bitmap : nil
  end
end



class PokeSelectionSprite < SpriteWrapper
  attr_reader :selected
  attr_reader :preselected
  attr_reader :switching
  attr_reader :pokemon
  attr_reader :active
  attr_accessor :text

  def initialize(pokemon,index,viewport=nil)
    super(viewport)
    @pokemon=pokemon
    active=(index==0)
    @active=active
    if active # Rounded panel
      @deselbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRound")
      @selbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRoundSel")
      @deselfntbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRoundFnt")
      @selfntbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRoundSelFnt")
      @deselswapbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRoundSwap")
      @selswapbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRoundSelSwap")
    else # Rectangular panel
      @deselbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRect")
      @selbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRectSel")
      @deselfntbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRectFnt")
      @selfntbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRectSelFnt")
      @deselswapbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRectSwap")
      @selswapbitmap=AnimatedBitmap.new("Graphics/Pictures/partyPanelRectSelSwap")
    end
    @spriteXOffset=28
    @spriteYOffset=0
    @pokeballXOffset=10
    @pokeballYOffset=0
    @pokenameX=96
    @pokenameY=16
    @levelX=20
    @levelY=62
    @statusX=80
    @statusY=68
    @genderX=224
    @genderY=16
    @hpX=224
    @hpY=60
    @hpbarX=96
    @hpbarY=50
    @gaugeX=128
    @gaugeY=52
    @itemXOffset=62
    @itemYOffset=48
    @annotX=96
    @annotY=58
    xvalues=[0,256,0,256,0,256]
    yvalues=[0,16,96,112,192,208]
    @text=nil
    @statuses=AnimatedBitmap.new(_INTL("Graphics/Pictures/statuses"))
    @hpbar=AnimatedBitmap.new("Graphics/Pictures/partyHP")
    @hpbarfnt=AnimatedBitmap.new("Graphics/Pictures/partyHPfnt")
    @hpbarswap=AnimatedBitmap.new("Graphics/Pictures/partyHPswap")
    @pokeballsprite=ChangelingSprite.new(0,0,viewport)
    @pokeballsprite.addBitmap("pokeballdesel","Graphics/Pictures/partyBall")
    @pokeballsprite.addBitmap("pokeballsel","Graphics/Pictures/partyBallSel")
    @pkmnsprite=PokemonIconSprite.new(pokemon,viewport)
    @pkmnsprite.active=active
    @itemsprite=ChangelingSprite.new(0,0,viewport)
    @itemsprite.addBitmap("itembitmap","Graphics/Pictures/item")
    @itemsprite.addBitmap("mailbitmap","Graphics/Pictures/mail")
    @spriteX=xvalues[index]
    @spriteY=yvalues[index]
    @refreshBitmap=true
    @refreshing=false 
    @preselected=false
    @switching=false
    @pkmnsprite.z=self.z+2 # For compatibility with RGSS2
    @itemsprite.z=self.z+3 # For compatibility with RGSS2
    @pokeballsprite.z=self.z+1 # For compatibility with RGSS2
    self.selected=false
    self.x=@spriteX
    self.y=@spriteY
    refresh
  end

  def dispose
    @selbitmap.dispose
    @statuses.dispose
    @hpbar.dispose
    @deselbitmap.dispose
    @itemsprite.dispose
    @pkmnsprite.dispose
    @pokeballsprite.dispose
    self.bitmap.dispose
    super
  end

  def selected=(value)
    @selected=value
    @refreshBitmap=true
    refresh
  end

  def text=(value)
    @text=value
    @refreshBitmap=true
    refresh
  end

  def pokemon=(value)
    @pokemon=value
    if @pkmnsprite && !@pkmnsprite.disposed?
      @pkmnsprite.pokemon=value
    end
    @refreshBitmap=true
    refresh
  end

  def preselected=(value)
    if value!=@preselected
      @preselected=value
      refresh
    end
  end

  def switching=(value)
    if value!=@switching
      @switching=value
      refresh
    end
  end

  def color=(value)
    super
    refresh
  end

  def x=(value)
    super
    refresh
  end

  def y=(value)
    super
    refresh
  end

  def hp
    return @pokemon.hp
  end

  def refresh
    return if @refreshing
    return if disposed?
    @refreshing=true
    if !self.bitmap || self.bitmap.disposed?
      self.bitmap=BitmapWrapper.new(@selbitmap.width,@selbitmap.height)
    end
    if @pkmnsprite && !@pkmnsprite.disposed?
      @pkmnsprite.x=self.x+@spriteXOffset
      @pkmnsprite.y=self.y+@spriteYOffset
      @pkmnsprite.color=pbSrcOver(@pkmnsprite.color,self.color)
      @pkmnsprite.selected=self.selected
    end
    if @pokeballsprite && !@pokeballsprite.disposed?
      @pokeballsprite.x=self.x+@pokeballXOffset
      @pokeballsprite.y=self.y+@pokeballYOffset
      @pokeballsprite.color=self.color
      @pokeballsprite.changeBitmap(self.selected ? "pokeballsel" : "pokeballdesel")
    end
    if @itemsprite && !@itemsprite.disposed?
      @itemsprite.visible=(@pokemon.item>0)
      if @itemsprite.visible
        @itemsprite.changeBitmap(@pokemon.mail ? "mailbitmap" : "itembitmap")
        @itemsprite.x=self.x+@itemXOffset
        @itemsprite.y=self.y+@itemYOffset
        @itemsprite.color=self.color
      end
    end
    if @refreshBitmap
      @refreshBitmap=false
      self.bitmap.clear if self.bitmap
      if self.selected
        if self.preselected
          self.bitmap.blt(0,0,@selswapbitmap.bitmap,Rect.new(0,0,@selswapbitmap.width,@selswapbitmap.height))
          self.bitmap.blt(0,0,@deselswapbitmap.bitmap,Rect.new(0,0,@deselswapbitmap.width,@deselswapbitmap.height))
        elsif @switching
          self.bitmap.blt(0,0,@selswapbitmap.bitmap,Rect.new(0,0,@selswapbitmap.width,@selswapbitmap.height))
        elsif @pokemon.hp<=0 && !@pokemon.isEgg?
          self.bitmap.blt(0,0,@selfntbitmap.bitmap,Rect.new(0,0,@selfntbitmap.width,@selfntbitmap.height))
        else
          self.bitmap.blt(0,0,@selbitmap.bitmap,Rect.new(0,0,@selbitmap.width,@selbitmap.height))
        end
      else
        if self.preselected
          self.bitmap.blt(0,0,@deselswapbitmap.bitmap,Rect.new(0,0,@deselswapbitmap.width,@deselswapbitmap.height))
        elsif @pokemon.hp<=0 && !@pokemon.isEgg?
          self.bitmap.blt(0,0,@deselfntbitmap.bitmap,Rect.new(0,0,@deselfntbitmap.width,@deselfntbitmap.height))
        else
          self.bitmap.blt(0,0,@deselbitmap.bitmap,Rect.new(0,0,@deselbitmap.width,@deselbitmap.height))
        end
      end
      base=Color.new(248,248,248)
      shadow=Color.new(40,40,40)
      pbSetSystemFont(self.bitmap)
      pokename=@pokemon.name
      textpos=[[pokename,@pokenameX,@pokenameY,0,base,shadow]]
      if !@pokemon.isEgg?
        if !@text || @text.length==0
          tothp=@pokemon.totalhp
          textpos.push([_ISPRINTF("{1: 3d}/{2: 3d}",@pokemon.hp,tothp),
             @hpX,@hpY,1,base,shadow])
          barbg=(@pokemon.hp<=0) ? @hpbarfnt : @hpbar
          barbg=(self.preselected || (self.selected && @switching)) ? @hpbarswap : barbg
          self.bitmap.blt(@hpbarX,@hpbarY,barbg.bitmap,Rect.new(0,0,@hpbar.width,@hpbar.height))
          hpgauge=@pokemon.totalhp==0 ? 0 : (self.hp*96/@pokemon.totalhp)
          hpgauge=1 if hpgauge==0 && self.hp>0
          hpzone=0
          hpzone=1 if self.hp<=(@pokemon.totalhp/2).floor
          hpzone=2 if self.hp<=(@pokemon.totalhp/4).floor
          hpcolors=[
             Color.new(24,192,32),Color.new(96,248,96),   # Green
             Color.new(232,168,0),Color.new(248,216,0),   # Orange
             Color.new(248,72,56),Color.new(248,152,152)  # Red
          ]
          # fill with HP color
          self.bitmap.fill_rect(@gaugeX,@gaugeY,hpgauge,2,hpcolors[hpzone*2])
          self.bitmap.fill_rect(@gaugeX,@gaugeY+2,hpgauge,4,hpcolors[hpzone*2+1])
          self.bitmap.fill_rect(@gaugeX,@gaugeY+6,hpgauge,2,hpcolors[hpzone*2])
          if @pokemon.hp==0 || @pokemon.status>0
            status=(@pokemon.hp==0) ? 5 : @pokemon.status-1
            statusrect=Rect.new(0,16*status,44,16)
            self.bitmap.blt(@statusX,@statusY,@statuses.bitmap,statusrect)
          end
        end
        if @pokemon.isMale?
          textpos.push([_INTL("♂"),@genderX,@genderY,0,Color.new(0,112,248),Color.new(120,184,232)])
        elsif @pokemon.isFemale?
          textpos.push([_INTL("♀"),@genderX,@genderY,0,Color.new(232,32,16),Color.new(248,168,184)])
        end
      end
      pbDrawTextPositions(self.bitmap,textpos)
      if !@pokemon.isEgg?
        pbSetSmallFont(self.bitmap)
        leveltext=[([_INTL("Lv.{1}",@pokemon.level),@levelX,@levelY,0,base,shadow])]
        pbDrawTextPositions(self.bitmap,leveltext)
      end
      if @text && @text.length>0
        pbSetSystemFont(self.bitmap)
        annotation=[[@text,@annotX,@annotY,0,base,shadow]]
        pbDrawTextPositions(self.bitmap,annotation)
      end
    end
    @refreshing=false
  end

  def update
    super
    @pokeballsprite.update if @pokeballsprite && !@pokeballsprite.disposed?
    @itemsprite.update if @itemsprite && !@itemsprite.disposed?
    if @pkmnsprite && !@pkmnsprite.disposed?
      @pkmnsprite.update
    end
  end
end


##############################


class PokemonScreen_Scene
  def pbShowCommands(helptext,commands,index=0)
    ret=-1
    helpwindow=@sprites["helpwindow"]
    helpwindow.visible=true
    using(cmdwindow=Window_CommandPokemon.new(commands)) {
       cmdwindow.z=@viewport.z+1
       cmdwindow.index=index
       pbBottomRight(cmdwindow)
       helpwindow.text=""
       helpwindow.resizeHeightToFit(helptext,Graphics.width-cmdwindow.width)
       helpwindow.text=helptext
       pbBottomLeft(helpwindow)
       loop do
         Graphics.update
         Input.update
         cmdwindow.update
         self.update
         if Input.trigger?(Input::B)
           pbPlayCancelSE()
           ret=-1
           break
         end
         if Input.trigger?(Input::C)
           pbPlayDecisionSE()
           ret=cmdwindow.index
           break
         end
       end
    }
    return ret
  end

  def update
    pbUpdateSpriteHash(@sprites)
  end

  def pbSetHelpText(helptext)
    helpwindow=@sprites["helpwindow"]
    pbBottomLeftLines(helpwindow,1)
    helpwindow.text=helptext
    helpwindow.width=398
    helpwindow.visible=true
  end

  def pbStartScene(party,starthelptext,annotations=nil,multiselect=false)
    @sprites={}
    @party=party
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z=99999
    @multiselect=multiselect
    addBackgroundPlane(@sprites,"partybg","partybg",@viewport)
    @sprites["messagebox"]=Window_AdvancedTextPokemon.new("")
    @sprites["helpwindow"]=Window_UnformattedTextPokemon.new(starthelptext)
    @sprites["messagebox"].viewport=@viewport
    @sprites["messagebox"].visible=false
    @sprites["messagebox"].letterbyletter=true
    @sprites["helpwindow"].viewport=@viewport
    @sprites["helpwindow"].visible=true
    pbBottomLeftLines(@sprites["messagebox"],2)
    pbBottomLeftLines(@sprites["helpwindow"],1)
    pbSetHelpText(starthelptext)
    # Add party Pokémon sprites
    for i in 0...6
      if @party[i]
        @sprites["pokemon#{i}"]=PokeSelectionSprite.new(
           @party[i],i,@viewport)
      else
        @sprites["pokemon#{i}"]=PokeSelectionPlaceholderSprite.new(
           @party[i],i,@viewport)
      end
      if annotations
        @sprites["pokemon#{i}"].text=annotations[i]
      end
    end
    if @multiselect
      @sprites["pokemon6"]=PokeSelectionConfirmSprite.new(@viewport)
      @sprites["pokemon7"]=PokeSelectionCancelSprite2.new(@viewport)
    else
      @sprites["pokemon6"]=PokeSelectionCancelSprite.new(@viewport)
    end
    # Select first Pokémon
    @activecmd=0
    @sprites["pokemon0"].selected=true
    pbFadeInAndShow(@sprites) { update }
  end

  def pbEndScene
    pbFadeOutAndHide(@sprites) { update }
    pbDisposeSpriteHash(@sprites)
    @viewport.dispose
  end

  def pbChangeSelection(key,currentsel)
    numsprites=(@multiselect) ? 8 : 7 
    case key
    when Input::LEFT
      begin
        currentsel-=1
      end while currentsel>0 && currentsel<@party.length && !@party[currentsel]
      if currentsel>=@party.length && currentsel<6
        currentsel=@party.length-1
      end
      currentsel=numsprites-1 if currentsel<0
    when Input::RIGHT
      begin
        currentsel+=1
      end while currentsel<@party.length && !@party[currentsel]
      if currentsel==@party.length
        currentsel=6
      elsif currentsel==numsprites
        currentsel=0
      end
    when Input::UP
      if currentsel>=6
        begin
          currentsel-=1
        end while currentsel>0 && !@party[currentsel]
      else
        begin
          currentsel-=2
        end while currentsel>0 && !@party[currentsel]
      end
      if currentsel>=@party.length && currentsel<6
        currentsel=@party.length-1
      end
      currentsel=numsprites-1 if currentsel<0
    when Input::DOWN
      if currentsel>=5
        currentsel+=1
      else
        currentsel+=2
        currentsel=6 if currentsel<6 && !@party[currentsel]
      end
      if currentsel>=@party.length && currentsel<6
        currentsel=6
      elsif currentsel>=numsprites
        currentsel=0
      end
    end
    return currentsel
  end

  def pbRefresh
    for i in 0...6
      sprite=@sprites["pokemon#{i}"]
      if sprite 
        if sprite.is_a?(PokeSelectionSprite)
          sprite.pokemon=sprite.pokemon
        else
          sprite.refresh
        end
      end
    end
  end

  def pbRefreshSingle(i)
    sprite=@sprites["pokemon#{i}"]
    if sprite 
      if sprite.is_a?(PokeSelectionSprite)
        sprite.pokemon=sprite.pokemon
      else
        sprite.refresh
      end
    end
  end

  def pbHardRefresh
    oldtext=[]
    lastselected=-1
    for i in 0...6
      oldtext.push(@sprites["pokemon#{i}"].text)
      lastselected=i if @sprites["pokemon#{i}"].selected
      @sprites["pokemon#{i}"].dispose
    end
    lastselected=@party.length-1 if lastselected>=@party.length
    lastselected=0 if lastselected<0
    for i in 0...6
      if @party[i]
        @sprites["pokemon#{i}"]=PokeSelectionSprite.new(
        @party[i],i,@viewport)
      else
        @sprites["pokemon#{i}"]=PokeSelectionPlaceholderSprite.new(
        @party[i],i,@viewport)
      end
      @sprites["pokemon#{i}"].text=oldtext[i]
    end
    pbSelect(lastselected)
  end

  def pbPreSelect(pkmn)
    @activecmd=pkmn
  end

  def pbChoosePokemon(switching=false,initialsel=-1)
    for i in 0...6
      @sprites["pokemon#{i}"].preselected=(switching && i==@activecmd)
      @sprites["pokemon#{i}"].switching=switching
    end
    @activecmd=initialsel if initialsel>=0
    pbRefresh
    loop do
      Graphics.update
      Input.update
      self.update
      oldsel=@activecmd
      key=-1
      key=Input::DOWN if Input.repeat?(Input::DOWN)
      key=Input::RIGHT if Input.repeat?(Input::RIGHT)
      key=Input::LEFT if Input.repeat?(Input::LEFT)
      key=Input::UP if Input.repeat?(Input::UP)
      if key>=0
        @activecmd=pbChangeSelection(key,@activecmd)
      end
      if @activecmd!=oldsel # Changing selection
        pbPlayCursorSE()
        numsprites=(@multiselect) ? 8 : 7
        for i in 0...numsprites
          @sprites["pokemon#{i}"].selected=(i==@activecmd)
        end
      end
      if Input.trigger?(Input::B)
        return -1
      end
      if Input.trigger?(Input::C)
        pbPlayDecisionSE()
        cancelsprite=(@multiselect) ? 7 : 6
        return (@activecmd==cancelsprite) ? -1 : @activecmd
      end
    end
  end

  def pbSelect(item)
    @activecmd=item
    numsprites=(@multiselect) ? 8 : 7
    for i in 0...numsprites
      @sprites["pokemon#{i}"].selected=(i==@activecmd)
    end
  end

  def pbDisplay(text)
    @sprites["messagebox"].text=text
    @sprites["messagebox"].visible=true
    @sprites["helpwindow"].visible=false
    pbPlayDecisionSE()
    loop do
      Graphics.update
      Input.update
      self.update
      if @sprites["messagebox"].busy? && Input.trigger?(Input::C)
        pbPlayDecisionSE() if @sprites["messagebox"].pausing?
        @sprites["messagebox"].resume
      end
      if !@sprites["messagebox"].busy? &&
         (Input.trigger?(Input::C) || Input.trigger?(Input::B))
        break
      end
    end
    @sprites["messagebox"].visible=false
    @sprites["helpwindow"].visible=true
  end

  def pbSwitchBegin(oldid,newid)
    oldsprite=@sprites["pokemon#{oldid}"]
    newsprite=@sprites["pokemon#{newid}"]
    22.times do
      oldsprite.x+=(oldid&1)==0 ? -12 : 12
      newsprite.x+=(newid&1)==0 ? -12 : 12
      Graphics.update
      Input.update
      self.update
    end
  end
  
  def pbSwitchEnd(oldid,newid)
    oldsprite=@sprites["pokemon#{oldid}"]
    newsprite=@sprites["pokemon#{newid}"]
    oldsprite.pokemon=@party[oldid]
    newsprite.pokemon=@party[newid]
    22.times do
      oldsprite.x-=(oldid&1)==0 ? -12 : 12
      newsprite.x-=(newid&1)==0 ? -12 : 12
      Graphics.update
      Input.update
      self.update
    end
    for i in 0...6
      @sprites["pokemon#{i}"].preselected=false
      @sprites["pokemon#{i}"].switching=false
    end
    pbRefresh
  end

  def pbDisplayConfirm(text)
    ret=-1
    @sprites["messagebox"].text=text
    @sprites["messagebox"].visible=true
    @sprites["helpwindow"].visible=false
    using(cmdwindow=Window_CommandPokemon.new([_INTL("是"),_INTL("否")])){
       cmdwindow.z=@viewport.z+1
       cmdwindow.visible=false
       pbBottomRight(cmdwindow)
       cmdwindow.y-=@sprites["messagebox"].height
       loop do
         Graphics.update
         Input.update
         cmdwindow.visible=true if !@sprites["messagebox"].busy?
         cmdwindow.update
         self.update
         if Input.trigger?(Input::B) && !@sprites["messagebox"].busy?
           ret=false
           break
         end
         if Input.trigger?(Input::C) && @sprites["messagebox"].resume && !@sprites["messagebox"].busy?
           ret=(cmdwindow.index==0)
           break
         end
       end
    }
    @sprites["messagebox"].visible=false
    @sprites["helpwindow"].visible=true
    return ret
  end

  def pbAnnotate(annot)
    for i in 0...6
      if annot
        @sprites["pokemon#{i}"].text=annot[i]
      else
        @sprites["pokemon#{i}"].text=nil
      end
    end
  end

  def pbSummary(pkmnid)
    oldsprites=pbFadeOutAndHide(@sprites)
    scene=PokemonSummaryScene.new
    screen=PokemonSummary.new(scene)
    screen.pbStartScreen(@party,pkmnid)
    pbFadeInAndShow(@sprites,oldsprites)
  end

  def pbChooseItem(bag)
    oldsprites=pbFadeOutAndHide(@sprites)
    @sprites["helpwindow"].visible=false
    @sprites["messagebox"].visible=false
    scene=PokemonBag_Scene.new
    screen=PokemonBagScreen.new(scene,bag)
    ret=screen.pbGiveItemScreen
    pbFadeInAndShow(@sprites,oldsprites)
    return ret
  end

  def pbUseItem(bag,pokemon)
    oldsprites=pbFadeOutAndHide(@sprites)
    @sprites["helpwindow"].visible=false
    @sprites["messagebox"].visible=false
    scene=PokemonBag_Scene.new
    screen=PokemonBagScreen.new(scene,bag)
    ret=screen.pbUseItemScreen(pokemon)
    pbFadeInAndShow(@sprites,oldsprites)
    return ret
  end

  def pbMessageFreeText(text,startMsg,maxlength)
    return Kernel.pbMessageFreeText(
       _INTL("请输入留言（最多 {1} 个字符）。",maxlength),
       _INTL("{1}",startMsg),false,maxlength,Graphics.width) { update }
  end
end


######################################


class PokemonScreen
  def initialize(scene,party)
    @party=party
    @scene=scene
  end

  def pbHardRefresh
    @scene.pbHardRefresh
  end

  def pbRefresh
    @scene.pbRefresh
  end

  def pbRefreshSingle(i)
    @scene.pbRefreshSingle(i)
  end

  def pbDisplay(text)
    @scene.pbDisplay(text)
  end

  def pbConfirm(text)
    return @scene.pbDisplayConfirm(text)
  end

  def pbSwitch(oldid,newid)
    if oldid!=newid
      @scene.pbSwitchBegin(oldid,newid)
      tmp=@party[oldid]
      @party[oldid]=@party[newid]
      @party[newid]=tmp
      @scene.pbSwitchEnd(oldid,newid)
    end
  end

  def pbMailScreen(item,pkmn,pkmnid)
    message=""
    loop do
      message=@scene.pbMessageFreeText(
         _INTL("请输入信息（最多 256 个字符）。"),"",256)
      if message!=""
        # Store mail if a message was written
        poke1=poke2=poke3=nil
        if $Trainer.party[pkmnid+2]
          p=$Trainer.party[pkmnid+2]
          poke1=[p.species,p.gender,p.isShiny?,(p.form rescue 0),(p.isShadow? rescue false)]
          poke1.push(true) if p.isEgg?
        end
        if $Trainer.party[pkmnid+1]
          p=$Trainer.party[pkmnid+1]
          poke2=[p.species,p.gender,p.isShiny?,(p.form rescue 0),(p.isShadow? rescue false)]
          poke2.push(true) if p.isEgg?
        end
        poke3=[pkmn.species,pkmn.gender,pkmn.isShiny?,(pkmn.form rescue 0),(pkmn.isShadow? rescue false)]
        poke3.push(true) if pkmn.isEgg?
        pbStoreMail(pkmn,item,message,poke1,poke2,poke3)
        return true
      else
        return false if pbConfirm(_INTL("要停止给宝可梦邮件吗？"))
      end
    end
  end

  def pbTakeMail(pkmn)
    if !pkmn.hasItem?
      pbDisplay(_INTL("{1} 没有拿着任何东西。",pkmn.name))
    elsif !$PokemonBag.pbCanStore?(pkmn.item)
      pbDisplay(_INTL("背包已满，无法取下宝可梦的道具。"))
    elsif pkmn.mail
      if pbConfirm(_INTL("要把取下的邮件送到电脑吗？"))
        if !pbMoveToMailbox(pkmn)
          pbDisplay(_INTL("电脑的信箱已满。"))
        else
          pbDisplay(_INTL("邮件已送到电脑。"))
          pkmn.setItem(0)
        end
      elsif pbConfirm(_INTL("移除邮件后，信件内容会丢失。确定吗？"))
        pbDisplay(_INTL("已从宝可梦身上取下邮件。"))
        $PokemonBag.pbStoreItem(pkmn.item)
        pkmn.setItem(0)
        pkmn.mail=nil
      end
    else
      $PokemonBag.pbStoreItem(pkmn.item)
      itemname=PBItems.getName(pkmn.item)
      pbDisplay(_INTL("从 {2} 处获得了 {1}。",itemname,pkmn.name))
      pkmn.setItem(0)
    end
  end

  def pbGiveMail(item,pkmn,pkmnid=0)
    thisitemname=PBItems.getName(item)
    if pkmn.isEgg?
      pbDisplay(_INTL("蛋不能携带道具。"))
      return false
    elsif pkmn.mail
      pbDisplay(_INTL("要给予道具，必须先取下 {1} 的邮件。",pkmn.name))
      return false
    end
    if pkmn.item!=0
      itemname=PBItems.getName(pkmn.item)
      pbDisplay(_INTL("{1} 已经拿着 {2}。",pkmn.name,itemname))
      if pbConfirm(_INTL("要交换这两个道具吗？"))
        $PokemonBag.pbDeleteItem(item)
        if !$PokemonBag.pbStoreItem(pkmn.item)
          if !$PokemonBag.pbStoreItem(item) # Compensate
            raise _INTL("无法把已删除的道具放回背包")
          end
          pbDisplay(_INTL("背包已满，无法取下宝可梦的道具。"))
        else
          if pbIsMail?(item)
            if pbMailScreen(item,pkmn,pkmnid)
              pkmn.setItem(item)
              pbDisplay(_INTL("已取走 {1}，换成了 {2}。",itemname,thisitemname))
              return true
            else
              if !$PokemonBag.pbStoreItem(item) # Compensate
                raise _INTL("无法把已删除的道具放回背包")
              end
            end
          else
            pkmn.setItem(item)
            pbDisplay(_INTL("取走了宝可梦的 {1}，给了它 {2}。",itemname,thisitemname))
            return true
          end
        end
      end
    else
      if !pbIsMail?(item) || pbMailScreen(item,pkmn,pkmnid) # Open the mail screen if necessary
        $PokemonBag.pbDeleteItem(item)
        pkmn.setItem(item)
        pbDisplay(_INTL("宝可梦现在拿着 {1}。",thisitemname))
        return true
      end
    end
    return false
  end

  def pbPokemonGiveScreen(item)
    @scene.pbStartScene(@party,_INTL("给予哪只宝可梦？"))
    pkmnid=@scene.pbChoosePokemon
    ret=false
    if pkmnid>=0
      ret=pbGiveMail(item,@party[pkmnid],pkmnid)
    end
    pbRefreshSingle(pkmnid)
    @scene.pbEndScene
    return ret
  end

  def pbPokemonGiveMailScreen(mailIndex)
    @scene.pbStartScene(@party,_INTL("给予哪只宝可梦？"))
    pkmnid=@scene.pbChoosePokemon
    if pkmnid>=0
      pkmn=@party[pkmnid]
      if pkmn.item!=0 || pkmn.mail
        pbDisplay(_INTL("这只宝可梦已携带道具，不能再携带邮件。"))
      elsif pkmn.isEgg?
        pbDisplay(_INTL("蛋不能携带邮件。"))
      else
        pbDisplay(_INTL("邮件已从信箱中取出。"))
        pkmn.mail=$PokemonGlobal.mailbox[mailIndex]
        pkmn.setItem(pkmn.mail.item)
        $PokemonGlobal.mailbox.delete_at(mailIndex)
        pbRefreshSingle(pkmnid)
      end
    end
    @scene.pbEndScene
  end

  def pbStartScene(helptext,doublebattle,annotations=nil)
    @scene.pbStartScene(@party,helptext,annotations)
  end

  def pbChoosePokemon(helptext=nil)
    @scene.pbSetHelpText(helptext) if helptext
    return @scene.pbChoosePokemon
  end

  def pbChooseMove(pokemon,helptext)
    movenames=[]
    for i in pokemon.moves
      break if i.id==0
      if i.totalpp==0
        movenames.push(_INTL("{1}（PP：---）",PBMoves.getName(i.id),i.pp,i.totalpp))
      else
        movenames.push(_INTL("{1}（PP：{2}/{3}）",PBMoves.getName(i.id),i.pp,i.totalpp))
      end
    end
    return @scene.pbShowCommands(helptext,movenames)
  end

  def pbEndScene
    @scene.pbEndScene
  end

  # Checks for identical species
  def pbCheckSpecies(array)
    for i in 0...array.length
      for j in i+1...array.length
        return false if array[i].species==array[j].species
      end
    end
    return true
  end

# Checks for identical held items
  def pbCheckItems(array)
    for i in 0...array.length
      next if !array[i].hasItem?
      for j in i+1...array.length
        return false if array[i].item==array[j].item
      end
    end
    return true
  end

  def pbPokemonMultipleEntryScreenEx(ruleset)
    annot=[]
    statuses=[]
    ordinals=[
       _INTL("不符合条件"),
       _INTL("未进入"),
       _INTL("禁用"),
       _INTL("第一"),
       _INTL("第二"),
       _INTL("第三"),
       _INTL("第四"),
       _INTL("第五"),
       _INTL("第六")
    ]
    if !ruleset.hasValidTeam?(@party)
      return nil
    end
    ret=nil
    addedEntry=false
    for i in 0...@party.length
      if ruleset.isPokemonValid?(@party[i])
        statuses[i]=1
      else
        statuses[i]=2
      end  
    end
    for i in 0...@party.length
      annot[i]=ordinals[statuses[i]]
    end
    @scene.pbStartScene(@party,_INTL("选择宝可梦并确认。"),annot,true)
    loop do
      realorder=[]
      for i in 0...@party.length
        for j in 0...@party.length
          if statuses[j]==i+3
            realorder.push(j)
            break
          end
        end
      end
      for i in 0...realorder.length
        statuses[realorder[i]]=i+3
      end
      for i in 0...@party.length
        annot[i]=ordinals[statuses[i]]
      end
      @scene.pbAnnotate(annot)
      if realorder.length==ruleset.number && addedEntry
        @scene.pbSelect(6)
      end
      @scene.pbSetHelpText(_INTL("选择宝可梦并确认。"))
      pkmnid=@scene.pbChoosePokemon
      addedEntry=false
      if pkmnid==6 # Confirm was chosen
        ret=[]
        for i in realorder
          ret.push(@party[i])
        end
        error=[]
        if !ruleset.isValid?(ret,error)
          pbDisplay(error[0])
          ret=nil
        else
          break
        end
      end
      if pkmnid<0 # Canceled
        break
      end
      cmdEntry=-1
      cmdNoEntry=-1
      cmdSummary=-1
      commands=[]
      if (statuses[pkmnid] || 0) == 1
        commands[cmdEntry=commands.length]=_INTL("入口")
      elsif (statuses[pkmnid] || 0) > 2
        commands[cmdNoEntry=commands.length]=_INTL("禁止进入")
      end
      pkmn=@party[pkmnid]
      commands[cmdSummary=commands.length]=_INTL("查看详情")
      commands[commands.length]=_INTL("取消")
      command=@scene.pbShowCommands(_INTL("要对 {1} 做什么？",pkmn.name),commands) if pkmn
      if cmdEntry>=0 && command==cmdEntry
        if realorder.length>=ruleset.number && ruleset.number>0
          pbDisplay(_INTL("最多只能有 {1} 只宝可梦上场。",ruleset.number))
        else
          statuses[pkmnid]=realorder.length+3
          addedEntry=true
          pbRefreshSingle(pkmnid)
        end
      elsif cmdNoEntry>=0 && command==cmdNoEntry
        statuses[pkmnid]=1
        pbRefreshSingle(pkmnid)
      elsif cmdSummary>=0 && command==cmdSummary
        @scene.pbSummary(pkmnid)
      end
    end
    @scene.pbEndScene
    return ret
  end

  def pbChooseAblePokemon(ableProc,allowIneligible=false)
    annot=[]
    eligibility=[]
    for pkmn in @party
      elig=ableProc.call(pkmn)
      eligibility.push(elig)
      annot.push(elig ? _INTL("可") : _INTL("不可"))
    end
    ret=-1
    @scene.pbStartScene(@party,
       @party.length>1 ? _INTL("选择一只宝可梦。") : _INTL("选择宝可梦或取消。"),annot)
    loop do
      @scene.pbSetHelpText(
         @party.length>1 ? _INTL("选择一只宝可梦。") : _INTL("选择宝可梦或取消。"))
      pkmnid=@scene.pbChoosePokemon
      if pkmnid<0
        break
      elsif !eligibility[pkmnid] && !allowIneligible
        pbDisplay(_INTL("不能选择这只宝可梦。"))
      else
        ret=pkmnid
        break
      end
    end
    @scene.pbEndScene
    return ret
  end

  def pbRefreshAnnotations(ableProc)   # For after using an evolution stone
    annot=[]
    for pkmn in @party
      elig=ableProc.call(pkmn)
      annot.push(elig ? _INTL("可") : _INTL("不可"))
    end
    @scene.pbAnnotate(annot)
  end

  def pbClearAnnotations
    @scene.pbAnnotate(nil)
  end

  def pbPokemonDebug(pkmn,pkmnid)
    command=0
    loop do
      command=@scene.pbShowCommands(_INTL("要对 {1} 做什么？",pkmn.name),[
         _INTL("HP／状态"),
         _INTL("等级"),
         _INTL("种类"),
         _INTL("招式"),
         _INTL("性别"),
         _INTL("特性"),
         _INTL("性格"),
         _INTL("闪光"),
         _INTL("形态"),
         _INTL("亲密度"),
         _INTL("努力值／个体值／玩家ID"),
         _INTL("波动"),
         _INTL("归属"),
         _INTL("昵称"),
         _INTL("精灵球"),
         _INTL("缎带"),
         _INTL("蛋"),
         _INTL("暗影宝可梦"),
         _INTL("制作神秘礼物"),
         _INTL("复制"),
         _INTL("删除"),
         _INTL("取消")
      ],command)
      case command
      ### Cancel ###
      when -1, 21
        break
      ### HP/Status ###
      when 0
        cmd=0
        loop do
          cmd=@scene.pbShowCommands(_INTL("要对 {1} 做什么？",pkmn.name),[
             _INTL("设置 HP"),
             _INTL("状态：睡眠"),
             _INTL("状态：中毒"),
             _INTL("状态：灼伤"),
             _INTL("状态：麻痹"),
             _INTL("状态：冰冻"),
             _INTL("失去意识"),
             _INTL("回复")
          ],cmd)
          # Break
          if cmd==-1
            break
          # Set HP
          elsif cmd==0
            params=ChooseNumberParams.new
            params.setRange(0,pkmn.totalhp)
            params.setDefaultValue(pkmn.hp)
            newhp=Kernel.pbMessageChooseNumber(
               _INTL("设置宝可梦的 HP（最大 {1}）。",pkmn.totalhp),params) { @scene.update }
            if newhp!=pkmn.hp
              pkmn.hp=newhp
              pbDisplay(_INTL("{1} 的 HP 已设为 {2}。",pkmn.name,pkmn.hp))
              pbRefreshSingle(pkmnid)
            end
          # Set status
          elsif cmd>=1 && cmd<=5
            if pkmn.hp>0
              pkmn.status=cmd
              pkmn.statusCount=0
              if pkmn.status==PBStatuses::SLEEP
                params=ChooseNumberParams.new
                params.setRange(0,9)
                params.setDefaultValue(0)
                sleep=Kernel.pbMessageChooseNumber(
                   _INTL("设置该宝可梦的睡眠回合数。"),params) { @scene.update }
                pkmn.statusCount=sleep
              end
              pbDisplay(_INTL("{1} 的状态已修改。",pkmn.name))
              pbRefreshSingle(pkmnid)
            else
              pbDisplay(_INTL("{1} 的状态无法修改。",pkmn.name))
            end
          # Faint
          elsif cmd==6
            pkmn.hp=0
            pbDisplay(_INTL("{1} 的 HP 已设为 0。",pkmn.name))
            pbRefreshSingle(pkmnid)
          # Heal
          elsif cmd==7
            pkmn.heal
            pbDisplay(_INTL("{1} 已完全治愈。",pkmn.name))
            pbRefreshSingle(pkmnid)
          end
        end
      ### Level ###
      when 1
        params=ChooseNumberParams.new
        params.setRange(1,PBExperience::MAXLEVEL)
        params.setDefaultValue(pkmn.level)
        level=Kernel.pbMessageChooseNumber(
           _INTL("设置宝可梦的等级（最大 {1}）。",PBExperience::MAXLEVEL),params) { @scene.update }
        if level!=pkmn.level
          pkmn.level=level
          pkmn.calcStats
          pbDisplay(_INTL("{1} 的等级已设为 {2}。",pkmn.name,pkmn.level))
          pbRefreshSingle(pkmnid)
        end
      ### Species ###
      when 2
        species=pbChooseSpecies(pkmn.species)
        if species!=0
          oldspeciesname=PBSpecies.getName(pkmn.species)
          pkmn.species=species
          pkmn.calcStats
          oldname=pkmn.name
          pkmn.name=PBSpecies.getName(pkmn.species) if pkmn.name==oldspeciesname
          pbDisplay(_INTL("{1} 的种类已改为 {2}。",oldname,PBSpecies.getName(pkmn.species)))
          pbSeenForm(pkmn)
          pbRefreshSingle(pkmnid)
        end
      ### Moves ###
      when 3
        cmd=0
        loop do
          cmd=@scene.pbShowCommands(_INTL("要对 {1} 做什么？",pkmn.name),[
             _INTL("教授招式"),
             _INTL("遗忘招式"),
             _INTL("重置招式列表"),
             _INTL("重置初始招式")],cmd)
          # Break
          if cmd==-1
            break
          # Teach move
          elsif cmd==0
            move=pbChooseMoveList
            if move!=0
              pbLearnMove(pkmn,move)
              pbRefreshSingle(pkmnid)
            end
          # Forget move
          elsif cmd==1
            move=pbChooseMove(pkmn,_INTL("选择要忘记的招式。"))
            if move>=0
              movename=PBMoves.getName(pkmn.moves[move].id)
              pkmn.pbDeleteMoveAtIndex(move)
              pbDisplay(_INTL("{1} 忘记了 {2}。",pkmn.name,movename))
              pbRefreshSingle(pkmnid)
            end
          # Reset movelist
          elsif cmd==2
            pkmn.resetMoves
            pbDisplay(_INTL("{1} 的招式已重置。",pkmn.name))
            pbRefreshSingle(pkmnid)
          # Reset initial moves
          elsif cmd==3
            pkmn.pbRecordFirstMoves
            pbDisplay(_INTL("{1} 的招式已设为其最初学会的招式。",pkmn.name))
            pbRefreshSingle(pkmnid)
          end
        end
      ### Gender ###
      when 4
        if pkmn.gender==2
          pbDisplay(_INTL("{1} 没有性别。",pkmn.name))
        else
          cmd=0
          loop do
            oldgender=(pkmn.isMale?) ? _INTL("雄性") : _INTL("雌性")
            msg=[_INTL("性别 {1} 是自然获得的。",oldgender),
                 _INTL("性别 {1} 已被强制指定。",oldgender)][pkmn.genderflag ? 1 : 0]
            cmd=@scene.pbShowCommands(msg,[
               _INTL("设为男性"),
               _INTL("设为女性"),
               _INTL("移除覆盖")],cmd)
            # Break
            if cmd==-1
              break
            # Make male
            elsif cmd==0
              pkmn.setGender(0)
              if pkmn.isMale?
                pbDisplay(_INTL("{1} 现在是雄性。",pkmn.name))
              else
                pbDisplay(_INTL("{1} 的性别无法修改。",pkmn.name))
              end
            # Make female
            elsif cmd==1
              pkmn.setGender(1)
              if pkmn.isFemale?
                pbDisplay(_INTL("{1} 现在是雌性。",pkmn.name))
              else
                pbDisplay(_INTL("{1} 的性别无法修改。",pkmn.name))
              end
            # Remove override
            elsif cmd==2
              pkmn.genderflag=nil
              pbDisplay(_INTL("已移除性别覆盖。"))
            end
            pbSeenForm(pkmn)
            pbRefreshSingle(pkmnid)
          end
        end
      ### Ability ###
      when 5
        cmd=0
        loop do
          abils=pkmn.getAbilityList
          oldabil=PBAbilities.getName(pkmn.ability)
          commands=[]
          for i in abils
            commands.push((i[1]<2 ? "" : "(H) ")+PBAbilities.getName(i[0]))
          end
          commands.push(_INTL("移除覆盖"))
          msg=[_INTL("特性 {1} 是自然获得的。",oldabil),
               _INTL("特性 {1} 已被强制指定。",oldabil)][pkmn.abilityflag!=nil ? 1 : 0]
          cmd=@scene.pbShowCommands(msg,commands,cmd)
          # Break
          if cmd==-1
            break
          # Set ability override
          elsif cmd>=0 && cmd<abils.length
            pkmn.setAbility(abils[cmd][1])
          # Remove override
          elsif cmd==abils.length
            pkmn.abilityflag=nil
          end
          pbRefreshSingle(pkmnid)
        end
      ### Nature ###
      when 6
        cmd=0
        loop do
          oldnature=PBNatures.getName(pkmn.nature)
          commands=[]
          (PBNatures.getCount).times do |i|
            commands.push(PBNatures.getName(i))
          end
          commands.push(_INTL("移除覆盖"))
          msg=[_INTL("性格 {1} 是自然获得的。",oldnature),
               _INTL("性格 {1} 已被强制指定。",oldnature)][pkmn.natureflag ? 1 : 0]
          cmd=@scene.pbShowCommands(msg,commands,cmd)
          # Break
          if cmd==-1
            break
          # Set nature override
          elsif cmd>=0 && cmd<PBNatures.getCount
            pkmn.setNature(cmd)
            pkmn.calcStats
          # Remove override
          elsif cmd==PBNatures.getCount
            pkmn.natureflag=nil
          end
          pbRefreshSingle(pkmnid)
        end
      ### Shininess ###
      when 7
        cmd=0
        loop do
          oldshiny=(pkmn.isShiny?) ? _INTL("闪光") : _INTL("普通")
          msg=[_INTL("闪光（{1}）是自然获得的。",oldshiny),
               _INTL("闪光（{1}）已被强制指定。",oldshiny)][pkmn.shinyflag!=nil ? 1 : 0]
          cmd=@scene.pbShowCommands(msg,[
               _INTL("设为闪光"),
               _INTL("设为普通（无闪光）"),
               _INTL("移除覆盖")],cmd)
          # Break
          if cmd==-1
            break
          # Make shiny
          elsif cmd==0
            pkmn.makeShiny
          # Make normal
          elsif cmd==1
            pkmn.makeNotShiny
          # Remove override
          elsif cmd==2
            pkmn.shinyflag=nil
          end
          pbRefreshSingle(pkmnid)
        end
      ### Form ###
      when 8
        params=ChooseNumberParams.new
        params.setRange(0,100)
        params.setDefaultValue(pkmn.form)
        f=Kernel.pbMessageChooseNumber(
           _INTL("设置该宝可梦的形态。"),params) { @scene.update }
        if f!=pkmn.form
          pkmn.form=f
          pbDisplay(_INTL("{1} 的形态已设为 {2}。",pkmn.name,pkmn.form))
          pbSeenForm(pkmn)
          pbRefreshSingle(pkmnid)
        end
      ### Happiness ###
      when 9
        params=ChooseNumberParams.new
        params.setRange(0,255)
        params.setDefaultValue(pkmn.happiness)
        h=Kernel.pbMessageChooseNumber(
           _INTL("设置该宝可梦的亲密度（最高 255）。"),params) { @scene.update }
        if h!=pkmn.happiness
          pkmn.happiness=h
          pbDisplay(_INTL("{1} 的亲密度已设为 {2}。",pkmn.name,pkmn.happiness))
          pbRefreshSingle(pkmnid)
        end
      ### EV/IV/pID ###
      when 10
        stats=[_INTL("HP"),_INTL("攻击"),_INTL("防御"),
               _INTL("速度"),_INTL("特攻"),_INTL("特防")]
        cmd=0
        loop do
          persid=sprintf("0x%08X",pkmn.personalID)
          cmd=@scene.pbShowCommands(_INTL("个人 ID 为 {1}。",persid),[
             _INTL("设置努力值"),
             _INTL("设置个体值"),
             _INTL("随机 pID")],cmd)
          case cmd
          # Break
          when -1
            break
          # Set EVs
          when 0
            cmd2=0
            loop do
              evcommands=[]
              for i in 0...stats.length
                evcommands.push(stats[i]+" (#{pkmn.ev[i]})")
              end
              cmd2=@scene.pbShowCommands(_INTL("要修改哪个努力值？"),evcommands,cmd2)
              if cmd2==-1
                break
              elsif cmd2>=0 && cmd2<stats.length
                params=ChooseNumberParams.new
                params.setRange(0,PokeBattle_Pokemon::EVSTATLIMIT)
                params.setDefaultValue(pkmn.ev[cmd2])
                params.setCancelValue(pkmn.ev[cmd2])
                f=Kernel.pbMessageChooseNumber(
                   _INTL("设置 {1} 的 EV（最大 {2}）。",
                      stats[cmd2],PokeBattle_Pokemon::EVSTATLIMIT),params) { @scene.update }
                pkmn.ev[cmd2]=f
                pkmn.totalhp
                pkmn.calcStats
                pbRefreshSingle(pkmnid)
              end
            end
          # Set IVs
          when 1
            cmd2=0
            loop do
              hiddenpower=pbHiddenPower(pkmn.iv)
              msg=_INTL("觉醒力量：\n{1}，威力 {2}。",PBTypes.getName(hiddenpower[0]),hiddenpower[1])
              ivcommands=[]
              for i in 0...stats.length
                ivcommands.push(stats[i]+" (#{pkmn.iv[i]})")
              end
              ivcommands.push(_INTL("全部随机"))
              cmd2=@scene.pbShowCommands(msg,ivcommands,cmd2)
              if cmd2==-1
                break
              elsif cmd2>=0 && cmd2<stats.length
                params=ChooseNumberParams.new
                params.setRange(0,31)
                params.setDefaultValue(pkmn.iv[cmd2])
                params.setCancelValue(pkmn.iv[cmd2])
                f=Kernel.pbMessageChooseNumber(
                   _INTL("设置 {1} 的 IV（最大 31）。",stats[cmd2]),params) { @scene.update }
                pkmn.iv[cmd2]=f
                pkmn.calcStats
                pbRefreshSingle(pkmnid)
              elsif cmd2==ivcommands.length-1
                pkmn.iv[0]=rand(32)
                pkmn.iv[1]=rand(32)
                pkmn.iv[2]=rand(32)
                pkmn.iv[3]=rand(32)
                pkmn.iv[4]=rand(32)
                pkmn.iv[5]=rand(32)
                pkmn.calcStats
                pbRefreshSingle(pkmnid)
              end
            end
          # Randomise pID
          when 2
            pkmn.personalID=rand(256)
            pkmn.personalID|=rand(256)<<8
            pkmn.personalID|=rand(256)<<16
            pkmn.personalID|=rand(256)<<24
            pkmn.calcStats
            pbRefreshSingle(pkmnid)
          end
        end
      ### Pokérus ###
      when 11
        cmd=0
        loop do
          pokerus=(pkmn.pokerus) ? pkmn.pokerus : 0
          msg=[_INTL("{1} 没有宝可病毒。",pkmn.name),
               _INTL("携带病毒株 {1}，还可传染 {2} 天。",pokerus/16,pokerus%16),
               _INTL("携带病毒株 {1}，已无传染性。",pokerus/16)][pkmn.pokerusStage]
          cmd=@scene.pbShowCommands(msg,[
               _INTL("给予随机血脉"),
               _INTL("设为不会感染波动"),
               _INTL("治愈波动")],cmd)
          # Break
          if cmd==-1
            break
          # Give random strain
          elsif cmd==0
            pkmn.givePokerus
          # Make not infectious
          elsif cmd==1
            strain=pokerus/16
            p=strain<<4
            pkmn.pokerus=p
          # Clear Pokérus
          elsif cmd==2
            pkmn.pokerus=0
          end
        end
      ### Ownership ###
      when 12
        cmd=0
        loop do
          gender=[_INTL("男性"),_INTL("女性"),_INTL("未知")][pkmn.otgender]
          msg=[_INTL("玩家的宝可梦\n{1}\n{2}\n{3}（{4}）",pkmn.ot,gender,pkmn.publicID,pkmn.trainerID),
               _INTL("外来宝可梦\n{1}\n{2}\n{3}（{4}）",pkmn.ot,gender,pkmn.publicID,pkmn.trainerID)
              ][pkmn.isForeign?($Trainer) ? 1 : 0]
          cmd=@scene.pbShowCommands(msg,[
               _INTL("设为玩家所有"),
               _INTL("设置初训家的名字"),
               _INTL("设置初训家的性别"),
               _INTL("随机信赖ID"),
               _INTL("设置信赖ID")],cmd)
          # Break
          if cmd==-1
            break
          # Make player's
          elsif cmd==0
            pkmn.trainerID=$Trainer.id
            pkmn.ot=$Trainer.name
            pkmn.otgender=$Trainer.gender
          # Set OT's name
          elsif cmd==1
            newot=pbEnterPlayerName(_INTL("{1} 的初训家名字？",pkmn.name),1,7)
            pkmn.ot=newot
          # Set OT's gender
          elsif cmd==2
            cmd2=@scene.pbShowCommands(_INTL("设置初训家的性别。"),
               [_INTL("男性"),_INTL("女性"),_INTL("未知")])
            pkmn.otgender=cmd2 if cmd2>=0
          # Random foreign ID
          elsif cmd==3
            pkmn.trainerID=$Trainer.getForeignID
          # Set foreign ID
          elsif cmd==4
            params=ChooseNumberParams.new
            params.setRange(0,65535)
            params.setDefaultValue(pkmn.publicID)
            val=Kernel.pbMessageChooseNumber(
               _INTL("设置新ID（最高 65535）。"),params) { @scene.update }
            pkmn.trainerID=val
            pkmn.trainerID|=val<<16
          end
        end
      ### Nickname ###
      when 13
        cmd=0
        loop do
          speciesname=PBSpecies.getName(pkmn.species)
          msg=[_INTL("{1} 的昵称是 {2}。",speciesname,pkmn.name),
               _INTL("{1} 没有昵称。",speciesname)][pkmn.name==speciesname ? 1 : 0]
          cmd=@scene.pbShowCommands(msg,[
               _INTL("重命名"),
               _INTL("清除名字")],cmd)
          # Break
          if cmd==-1
            break
          # Rename
          elsif cmd==0
            newname=pbEnterPokemonName(_INTL("{1} 的昵称？",speciesname),0,10,"",pkmn)
            pkmn.name=(newname=="") ? speciesname : newname
            pbRefreshSingle(pkmnid)
          # Erase name
          elsif cmd==1
            pkmn.name=speciesname
          end
        end
      ### Poké Ball ###
      when 14
        cmd=0
        loop do
          oldball=PBItems.getName(pbBallTypeToBall(pkmn.ballused))
          commands=[]; balls=[]
          for key in $BallTypes.keys
            item=getID(PBItems,$BallTypes[key])
            balls.push([key,PBItems.getName(item)]) if item && item>0
          end
          balls.sort! {|a,b| a[1]<=>b[1]}
          for i in 0...commands.length
            cmd=i if pkmn.ballused==balls[i][0]
          end
          for i in balls
            commands.push(i[1])
          end
          cmd=@scene.pbShowCommands(_INTL("使用了 {1}。",oldball),commands,cmd)
          if cmd==-1
            break
          else
            pkmn.ballused=balls[cmd][0]
          end
        end
      ### Ribbons ###
      when 15
        cmd=0
        loop do
          commands=[]
          for i in 1..PBRibbons.maxValue
            commands.push(_INTL("{1} {2}",
               pkmn.hasRibbon?(i) ? "[X]" : "[  ]",PBRibbons.getName(i)))
          end
          cmd=@scene.pbShowCommands(_INTL("{1} 枚奖章。",pkmn.ribbonCount),commands,cmd)
          if cmd==-1
            break
          elsif cmd>=0 && cmd<commands.length
            if pkmn.hasRibbon?(cmd+1)
              pkmn.takeRibbon(cmd+1)
            else
              pkmn.giveRibbon(cmd+1)
            end
          end
        end
      ### Egg ###
      when 16
        cmd=0
        loop do
          msg=[_INTL("不是蛋"),
               _INTL("蛋步数：{1}。",pkmn.eggsteps)][pkmn.isEgg? ? 1 : 0]
          cmd=@scene.pbShowCommands(msg,[
               _INTL("生成蛋"),
               _INTL("生成宝可梦"),
               _INTL("把剩余孵化步数设为 1")],cmd)
          # Break
          if cmd==-1
            break
          # Make egg
          elsif cmd==0
            if pbHasEgg?(pkmn.species) ||
               pbConfirm(_INTL("{1} 不能是蛋。仍要设为蛋吗？",PBSpecies.getName(pkmn.species)))
              pkmn.level=EGGINITIALLEVEL
              pkmn.calcStats
              pkmn.name=_INTL("蛋")
              dexdata=pbOpenDexData
              pbDexDataOffset(dexdata,pkmn.species,21)
              pkmn.eggsteps=dexdata.fgetw
              dexdata.close
              pkmn.hatchedMap=0
              pkmn.obtainMode=1
              pbRefreshSingle(pkmnid)
            end
          # Make Pokémon
          elsif cmd==1
            pkmn.name=PBSpecies.getName(pkmn.species)
            pkmn.eggsteps=0
            pkmn.hatchedMap=0
            pkmn.obtainMode=0
            pbRefreshSingle(pkmnid)
          # Set eggsteps to 1
          elsif cmd==2
            pkmn.eggsteps=1 if pkmn.eggsteps>0
          end
        end
      ### Shadow Pokémon ###
      when 17
        cmd=0
        loop do
          msg=[_INTL("不是暗影宝可梦。"),
               _INTL("心灵槽为 {1}。",pkmn.heartgauge)][(pkmn.isShadow? rescue false) ? 1 : 0]
          cmd=@scene.pbShowCommands(msg,[
             _INTL("生成暗影宝可梦"),
             _INTL("降低心之刻度")],cmd)
          # Break
          if cmd==-1
            break
          # Make Shadow
          elsif cmd==0
            if !(pkmn.isShadow? rescue false) && pkmn.respond_to?("makeShadow")
              pkmn.makeShadow
              pbDisplay(_INTL("{1} 现在是黑暗宝可梦。",pkmn.name))
              pbRefreshSingle(pkmnid)
            else
              pbDisplay(_INTL("{1} 已经是黑暗宝可梦。",pkmn.name))
            end
          # Lower heart gauge
          elsif cmd==1
            if (pkmn.isShadow? rescue false)
              prev=pkmn.heartgauge
              pkmn.adjustHeart(-700)
              Kernel.pbMessage(_INTL("{1} 的心灵槽从 {2} 降到 {3}（现在阶段 {4}）。",
                 pkmn.name,prev,pkmn.heartgauge,pkmn.heartStage))
              pbReadyToPurify(pkmn)
            else
              Kernel.pbMessage(_INTL("{1} 不是黑暗宝可梦。",pkmn.name))
            end
          end
        end
      ### Make Mystery Gift ###
      when 18
        pbCreateMysteryGift(0,pkmn)
      ### Duplicate ###
      when 19
        if pbConfirm(_INTL("确定要复制这只宝可梦吗？"))
          clonedpkmn=pkmn.clone
          clonedpkmn.iv=pkmn.iv.clone
          clonedpkmn.ev=pkmn.ev.clone
          pbStorePokemon(clonedpkmn)
          pbHardRefresh
          pbDisplay(_INTL("该宝可梦已复制。"))
          break
        end
      ### Delete ###
      when 20
        if pbConfirm(_INTL("确定要删除这只宝可梦吗？"))
          @party[pkmnid]=nil
          @party.compact!
          pbHardRefresh
          pbDisplay(_INTL("该宝可梦已删除。"))
          break
        end
      end
    end
  end

  def pbPokemonScreen
    @scene.pbStartScene(@party,@party.length>1 ? _INTL("选择一只宝可梦。") : _INTL("选择宝可梦或取消。"),nil)
    loop do
      @scene.pbSetHelpText(@party.length>1 ? _INTL("选择一只宝可梦。") : _INTL("选择宝可梦或取消。"))
      pkmnid=@scene.pbChoosePokemon
      break if pkmnid<0
      pkmn=@party[pkmnid]
      commands   = []
      cmdSummary = -1
      cmdDebug   = -1
      cmdMoves   = [-1,-1,-1,-1]
      cmdSwitch  = -1
      cmdMail    = -1
      cmdItem    = -1
      # Build the commands
      commands[cmdSummary=commands.length]      = _INTL("查看详情")
      commands[cmdDebug=commands.length]        = _INTL("调试") if $DEBUG
      for i in 0...pkmn.moves.length
        move=pkmn.moves[i]
        # Check for hidden moves and add any that were found
        if !pkmn.isEgg? && (isConst?(move.id,PBMoves,:MILKDRINK) ||
                            isConst?(move.id,PBMoves,:SOFTBOILED) ||
                            HiddenMoveHandlers.hasHandler(move.id))
          commands[cmdMoves[i]=commands.length] = PBMoves.getName(move.id)
        end
      end
      commands[cmdSwitch=commands.length]       = _INTL("交换") if @party.length>1
      if !pkmn.isEgg?
        if pkmn.mail
          commands[cmdMail=commands.length]     = _INTL("邮件")
        else
          commands[cmdItem=commands.length]     = _INTL("道具")
        end
      end
      commands[commands.length]                 = _INTL("取消")
      command=@scene.pbShowCommands(_INTL("要对 {1} 做什么？",pkmn.name),commands)
      havecommand=false
      for i in 0...4
        if cmdMoves[i]>=0 && command==cmdMoves[i]
          havecommand=true
          if isConst?(pkmn.moves[i].id,PBMoves,:SOFTBOILED) ||
             isConst?(pkmn.moves[i].id,PBMoves,:MILKDRINK)
            amt=[(pkmn.totalhp/5).floor,1].max
            if pkmn.hp<=amt
              pbDisplay(_INTL("HP 不足…"))
              break
            end
            @scene.pbSetHelpText(_INTL("对哪只宝可梦使用？"))
            oldpkmnid=pkmnid
            loop do
              @scene.pbPreSelect(oldpkmnid)
              pkmnid=@scene.pbChoosePokemon(true,pkmnid)
              break if pkmnid<0
              newpkmn=@party[pkmnid]
              if pkmnid==oldpkmnid
                pbDisplay(_INTL("{1} 不能对自己使用 {2}！",pkmn.name,PBMoves.getName(pkmn.moves[i].id)))
              elsif newpkmn.isEgg?
                pbDisplay(_INTL("{1} 不能用于蛋！",PBMoves.getName(pkmn.moves[i].id)))
              elsif newpkmn.hp==0 || newpkmn.hp==newpkmn.totalhp
                pbDisplay(_INTL("{1} 不能用于那只宝可梦。",PBMoves.getName(pkmn.moves[i].id)))
              else
                pkmn.hp-=amt
                hpgain=pbItemRestoreHP(newpkmn,amt)
                @scene.pbDisplay(_INTL("{1} 的 HP 恢复了 {2} 点。",newpkmn.name,hpgain))
                pbRefresh
              end
              break if pkmn.hp<=amt
            end
            break
          elsif Kernel.pbCanUseHiddenMove?(pkmn,pkmn.moves[i].id)
            @scene.pbEndScene
            if isConst?(pkmn.moves[i].id,PBMoves,:FLY)
              scene=PokemonRegionMapScene.new(-1,false)
              screen=PokemonRegionMap.new(scene)
              ret=screen.pbStartFlyScreen
              if ret
                $PokemonTemp.flydata=ret
                return [pkmn,pkmn.moves[i].id]
              end
              @scene.pbStartScene(@party,
                 @party.length>1 ? _INTL("选择一只宝可梦。") : _INTL("选择宝可梦或取消。"))
              break
            end
            return [pkmn,pkmn.moves[i].id]
          else
            break
          end
        end
      end
      next if havecommand
      if cmdSummary>=0 && command==cmdSummary
        @scene.pbSummary(pkmnid)
      elsif cmdDebug>=0 && command==cmdDebug
        pbPokemonDebug(pkmn,pkmnid)
      elsif cmdSwitch>=0 && command==cmdSwitch
        @scene.pbSetHelpText(_INTL("移动到哪？"))
        oldpkmnid=pkmnid
        pkmnid=@scene.pbChoosePokemon(true)
        if pkmnid>=0 && pkmnid!=oldpkmnid
          pbSwitch(oldpkmnid,pkmnid)
        end
      elsif cmdMail>=0 && command==cmdMail
        command=@scene.pbShowCommands(_INTL("要对邮件做什么？"),
           [_INTL("阅读"),_INTL("取出"),_INTL("取消")])
        case command
        when 0 # Read
          pbFadeOutIn(99999){
             pbDisplayMail(pkmn.mail,pkmn)
          }
        when 1 # Take
          pbTakeMail(pkmn)
          pbRefreshSingle(pkmnid)
        end
      elsif cmdItem>=0 && command==cmdItem
        itemcommands = []
        cmdUseItem   = -1
        cmdGiveItem  = -1
        cmdTakeItem  = -1
        cmdMoveItem  = -1
        # Build the commands
        itemcommands[cmdUseItem=itemcommands.length]  = _INTL("使用")
        itemcommands[cmdGiveItem=itemcommands.length] = _INTL("给予")
        itemcommands[cmdTakeItem=itemcommands.length] = _INTL("取出") if pkmn.hasItem?
        itemcommands[cmdMoveItem=itemcommands.length] = _INTL("移动") if pkmn.hasItem? && !pbIsMail?(pkmn.item)
        itemcommands[itemcommands.length]             = _INTL("取消")
        command=@scene.pbShowCommands(_INTL("要对道具做什么？"),itemcommands)
        if cmdUseItem>=0 && command==cmdUseItem   # Use
          item=@scene.pbUseItem($PokemonBag,pkmn)
          if item>0
            pbUseItemOnPokemon(item,pkmn,self)
            pbRefreshSingle(pkmnid)
          end
        elsif cmdGiveItem>=0 && command==cmdGiveItem   # Give
          item=@scene.pbChooseItem($PokemonBag)
          if item>0
            pbGiveMail(item,pkmn,pkmnid)
            pbRefreshSingle(pkmnid)
          end
        elsif cmdTakeItem>=0 && command==cmdTakeItem   # Take
          pbTakeMail(pkmn)
          pbRefreshSingle(pkmnid)
        elsif cmdMoveItem>=0 && command==cmdMoveItem   # Move
          item=pkmn.item
          itemname=PBItems.getName(item)
          @scene.pbSetHelpText(_INTL("把 {1} 给哪只宝可梦？",itemname))
          oldpkmnid=pkmnid
          loop do
            @scene.pbPreSelect(oldpkmnid)
            pkmnid=@scene.pbChoosePokemon(true,pkmnid)
            break if pkmnid<0
            newpkmn=@party[pkmnid]
            if pkmnid==oldpkmnid
              break
            elsif newpkmn.isEgg?
              pbDisplay(_INTL("蛋不能携带道具。"))
            elsif !newpkmn.hasItem?
              newpkmn.setItem(item)
              pkmn.setItem(0)
              pbRefresh
              pbDisplay(_INTL("{1} 被给予了 {2} 携带。",newpkmn.name,itemname))
              break
            elsif pbIsMail?(newpkmn.item)
              pbDisplay(_INTL("要给予道具，必须先取下 {1} 的邮件。",newpkmn.name))
            else
              newitem=newpkmn.item
              newitemname=PBItems.getName(newitem)
              pbDisplay(_INTL("{1} 已经拿着一个 {2}。",newpkmn.name,newitemname))
              if pbConfirm(_INTL("要交换这两个道具吗？"))
                newpkmn.setItem(item)
                pkmn.setItem(newitem)
                pbRefresh
                pbDisplay(_INTL("{1} 被给予了 {2} 携带。",newpkmn.name,itemname))
                pbDisplay(_INTL("{1} 被给予了 {2} 携带。",pkmn.name,newitemname))
                break
              end
            end
          end
        end
      end
    end
    @scene.pbEndScene
    return nil
  end  
end