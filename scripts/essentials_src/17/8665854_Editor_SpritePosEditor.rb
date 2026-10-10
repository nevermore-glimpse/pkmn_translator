def findBottom(bitmap)
  return 0 if !bitmap
  for i in 1..bitmap.height
    for j in 0..bitmap.width-1
      return bitmap.height-i if bitmap.get_pixel(j,bitmap.height-i).alpha>0
    end
  end
  return 0
end

def pbAutoPositionAll
  metrics = load_data("Data/metrics.dat")
  for i in 1..PBSpecies.maxValueF
    s = pbGetSpeciesFromFSpecies(i)
    Graphics.update if i%50==0
    bitmap1 = pbLoadSpeciesBitmap(s[0],false,s[1],false,false,true)
    bitmap2 = pbLoadSpeciesBitmap(s[0],false,s[1])
    if bitmap1 && bitmap1.bitmap
      metrics[0][i] = (bitmap1.height-(findBottom(bitmap1.bitmap)+1))/2
    end
    if bitmap2 && bitmap2.bitmap
      metrics[1][i] = (bitmap2.height-(findBottom(bitmap2.bitmap)+1))/2
      metrics[1][i] += 4 # Just because
    end
    bitmap1.dispose if bitmap1
    bitmap2.dispose if bitmap2
  end
  save_data(metrics,"Data/metrics.dat")
  pbSavePokemonData
  pbSavePokemonFormsData
end



class SpritePositioner
  def pbOpen
    @sprites = {}
    @viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z = 99999
    battlebg   = "Graphics/Battlebacks/battlebgIndoorA"
    enemybase  = "Graphics/Battlebacks/enemybaseIndoorA"
    playerbase = "Graphics/Battlebacks/playerbaseIndoorA"
    @sprites["battlebg"] = AnimatedPlane.new(@viewport)
    @sprites["battlebg"].setBitmap(battlebg)
    @sprites["battlebg"].z = 0
    @sprites["playerbase"] = IconSprite.new(
       PokeBattle_SceneConstants::PLAYERBASEX,
       PokeBattle_SceneConstants::PLAYERBASEY,@viewport)
    @sprites["playerbase"].setBitmap(playerbase)
    @sprites["playerbase"].x -= @sprites["playerbase"].bitmap.width/2 if @sprites["playerbase"].bitmap!=nil
    @sprites["playerbase"].y -= @sprites["playerbase"].bitmap.height if @sprites["playerbase"].bitmap!=nil
    @sprites["playerbase"].z = 1
    @sprites["enemybase"] = IconSprite.new(
       PokeBattle_SceneConstants::FOEBASEX,
       PokeBattle_SceneConstants::FOEBASEY,@viewport)
    @sprites["enemybase"].setBitmap(enemybase)
    @sprites["enemybase"].x -= @sprites["enemybase"].bitmap.width/2 if @sprites["enemybase"].bitmap!=nil
    @sprites["enemybase"].y -= @sprites["enemybase"].bitmap.height/2 if @sprites["enemybase"].bitmap!=nil
    @sprites["enemybase"].z = 1
    @sprites["shadow1"] = IconSprite.new(
       PokeBattle_SceneConstants::FOEBATTLER_X,
       PokeBattle_SceneConstants::FOEBATTLER_Y,@viewport)
    @sprites["shadow1"].setBitmap("Graphics/Pictures/Battle/object_shadow")
    @sprites["shadow1"].x -= @sprites["shadow1"].bitmap.width/2 if @sprites["shadow1"].bitmap!=nil
    @sprites["shadow1"].y -= @sprites["shadow1"].bitmap.height/2 if @sprites["shadow1"].bitmap!=nil
    @sprites["shadow1"].z = 3
    @sprites["shadow1"].visible = false
    @sprites["pokemon0"] = PokemonSprite.new(@viewport)
    @sprites["pokemon0"].setOffset(PictureOrigin::Bottom)
    @sprites["pokemon0"].x = PokeBattle_SceneConstants::PLAYERBATTLER_X
    @sprites["pokemon0"].z = 21
    @sprites["pokemon1"] = PokemonSprite.new(@viewport)
    @sprites["pokemon1"].setOffset(PictureOrigin::Bottom)
    @sprites["pokemon1"].x = PokeBattle_SceneConstants::FOEBATTLER_X
    @sprites["pokemon1"].z = 16
    @sprites["messagebox"] = IconSprite.new(0,Graphics.height-96,@viewport)
    @sprites["messagebox"].setBitmap("Graphics/Pictures/Battle/debug_message")
    @sprites["messagebox"].z = 4
    @sprites["messagebox"].visible = true
    @sprites["info"] = Window_UnformattedTextPokemon.new("")
    @sprites["info"].viewport = @viewport
    @sprites["info"].visible  = false
    @oldSpeciesIndex = 0
    @species = 0
    @metrics = load_data("Data/metrics.dat")
    @metricsChanged = false
    refresh
    @starting = true
  end

  def pbClose
    if @metricsChanged
      if Kernel.pbConfirmMessage(_INTL("Some metrics have been edited. Save changes?"))
        pbSaveMetrics
        @metricsChanged = false
      end
    end
    return if !Kernel.pbConfirmMessage(_INTL("Quit from the sprite positioner?"))
    pbFadeOutAndHide(@sprites) { update }
    pbDisposeSpriteHash(@sprites)
    @viewport.dispose
  end

  def pbSaveMetrics
    save_data(@metrics,"Data/metrics.dat")
    pbSavePokemonData
    pbSavePokemonFormsData
  end

  def update
    pbUpdateSpriteHash(@sprites)
  end

  def refresh
    if @species<=0
      @sprites["pokemon0"].visible = false
      @sprites["pokemon1"].visible = false
      @sprites["shadow1"].visible = false
      return
    end
    @sprites["pokemon0"].y = PokeBattle_SceneConstants::PLAYERBATTLER_Y
    @sprites["pokemon0"].y += getBattleSpriteMetricOffset(@species,0,@metrics)
    @sprites["pokemon0"].visible = true
    @sprites["pokemon1"].y = PokeBattle_SceneConstants::FOEBATTLER_Y
    @sprites["pokemon1"].y += getBattleSpriteMetricOffset(@species,1,@metrics)
    @sprites["pokemon1"].visible = true
    @sprites["shadow1"].visible = (@metrics[2][@species]>0)
  end

  def pbAutoPosition
    oldmetric0 = @metrics[0][@species]
    oldmetric1 = @metrics[1][@species]
    bitmap1 = @sprites["pokemon0"].bitmap
    bitmap2 = @sprites["pokemon1"].bitmap
    newmetric0 = (bitmap1.height-(findBottom(bitmap1)+1))/2
    newmetric1 = (bitmap2.height-(findBottom(bitmap2)+1))/2
    newmetric1 += 4 # Just because
    if newmetric0!=oldmetric0 || newmetric1!=oldmetric1
      @metrics[0][@species] = newmetric0
      @metrics[1][@species] = newmetric1
      @metricsChanged = true
      refresh
    end
  end

  def pbChangeSpecies(species)
    @species = species
    s = pbGetSpeciesFromFSpecies(@species)
    @sprites["pokemon0"].setSpeciesBitmap(s[0],false,s[1],false,false,true)
    @sprites["pokemon1"].setSpeciesBitmap(s[0],false,s[1],false,false,false)
  end

  def pbSetParameter(param)
    return if @species<=0
    if param==3
      pbAutoPosition
      return
    end
    sprite = (param==0) ? @sprites["pokemon0"] : @sprites["pokemon1"]
    altitude = @metrics[param][@species]
    oldaltitude = altitude
    @sprites["info"].visible = true
    loop do
      sprite.visible = (Graphics.frame_count%15)<12
      Graphics.update
      Input.update
      self.update
      @sprites["info"].setTextToFit("#{altitude}")
      if Input.repeat?(Input::UP)
        altitude = (param==2) ? altitude+1 : altitude-1
        altitude = [altitude,0].max if param==2
        @metrics[param][@species] = altitude
        refresh
      elsif Input.repeat?(Input::DOWN)
        altitude = (param==2) ? altitude-1 : altitude+1
        altitude = [altitude,0].max if param==2
        @metrics[param][@species] = altitude
        refresh
      elsif Input.repeat?(Input::B)
        @metrics[param][@species] = oldaltitude
        pbPlayCancelSE
        refresh
        break
      elsif Input.repeat?(Input::C)
        @metricsChanged = true if altitude!=oldaltitude
        pbPlayDecisionSE
        break
      end
    end
    @sprites["info"].visible = false
    sprite.visible = true
  end

  def pbSpecies
    if @starting
      pbFadeInAndShow(@sprites) { update }
      @starting = false
    end
    cw = Window_CommandPokemonEx.newEmpty(0,0,260,32+24*6,@viewport)
    cw.rowHeight = 24
    pbSetSmallFont(cw.contents)
    cw.x = Graphics.width-cw.width
    cw.y = Graphics.height-cw.height
    allspecies = []
    commands = []
    for i in 1..PBSpecies.maxValueF
      s = pbGetSpeciesFromFSpecies(i)
      name = PBSpecies.getName(s[0])
      name = _INTL("{1} (form {2})",name,s[1]) if s[1]>0
      allspecies.push([i,s[0],name]) if name!=""
    end
    allspecies.sort!{|a,b| a[1]==b[1] ? a[0]<=>b[0] : a[2]<=>b[2] }
    for s in allspecies
      commands.push(_INTL("{1} - {2}",s[1],s[2]))
    end
    cw.commands = commands
    cw.index    = @oldSpeciesIndex
    species = 0
    oldindex = -1
    loop do
      Graphics.update
      Input.update
      cw.update
      if cw.index!=oldindex
        oldindex = cw.index
        pbChangeSpecies(allspecies[cw.index][0])
        refresh
      end
      self.update
      if Input.trigger?(Input::B)
        pbChangeSpecies(0)
        refresh
        break
      elsif Input.trigger?(Input::C)
        pbChangeSpecies(allspecies[cw.index][0])
        species = allspecies[cw.index][0]
        break
      end
    end
    @oldSpeciesIndex = cw.index
    cw.dispose 
    return species
  end

  def pbMenu(species)
    pbChangeSpecies(species)
    refresh
    cw = Window_CommandPokemon.new([
       _INTL("Set Ally Position"),
       _INTL("Set Enemy Position"),
       _INTL("Set Enemy Altitude"),
       _INTL("Auto-Position Sprites")
    ])
    cw.x        = Graphics.width-cw.width
    cw.y        = Graphics.height-cw.height
    cw.viewport = @viewport
    ret = -1
    loop do
      Graphics.update
      Input.update
      cw.update
      self.update
      if Input.trigger?(Input::C)
        pbPlayDecisionSE
        ret = cw.index
        break
      elsif Input.trigger?(Input::B)
        pbPlayCancelSE
        break
      end
    end
    cw.dispose
    return ret
  end
end



class SpritePositionerScreen
  def initialize(scene)
    @scene = scene
  end

  def pbStart
    @scene.pbOpen
    loop do
      species = @scene.pbSpecies
      break if species<=0
      loop do
        command = @scene.pbMenu(species)
        break if command<0
        @scene.pbSetParameter(command)
      end
    end
    @scene.pbClose
  end
end