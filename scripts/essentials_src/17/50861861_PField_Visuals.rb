#===============================================================================
# Location signpost
#===============================================================================
class LocationWindow
  def initialize(name)
    @window = Window_AdvancedTextPokemon.new(name)
    @window.resizeToFit(name,Graphics.width)
    @window.x        = 0
    @window.y        = -@window.height
    @window.z        = 99999
    @window.viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
    @window.viewport.z = 600
    @currentmap = $game_map.map_id
    @frames = 0
  end

  def disposed?
    @window.disposed?
  end

  def dispose
    @window.dispose
  end

  def update
    return if @window.disposed?
    @window.update
    if $game_temp.message_window_showing || @currentmap!=$game_map.map_id
      @window.dispose
      return
    end
    if @frames>80
      @window.y -= 4
      @window.dispose if @window.y+@window.height<0
    else
      @window.y += 4 if @window.y<0
      @frames += 1
    end
  end
end



#===============================================================================
# Visibility circle in dark maps
#===============================================================================
class DarknessSprite < SpriteWrapper
  attr_reader :radius

  def initialize(viewport=nil)
    super(viewport)
    @darkness = BitmapWrapper.new(Graphics.width,Graphics.height)
    @radius = 64
    self.bitmap = @darkness
    self.z      = 99998
    refresh
  end

  def dispose
    @darkness.dispose
    super
  end

  def radius=(value)
    @radius = value
    refresh
  end

  def refresh
    @darkness.fill_rect(0,0,Graphics.width,Graphics.height,Color.new(0,0,0,255))
    cx = Graphics.width/2
    cy = Graphics.height/2
    cradius = @radius
    numfades = 5
    for i in 1..numfades
      for j in cx-cradius..cx+cradius
        diff2 = (cradius * cradius) - ((j - cx) * (j - cx))
        diff = Math.sqrt(diff2)
        @darkness.fill_rect(j,cy-diff,1,diff*2,Color.new(0,0,0,255.0*(numfades-i)/numfades))
      end
      cradius = (cradius*0.9).floor
    end
  end
end



#===============================================================================
# Lights
#===============================================================================
class LightEffect
  def initialize(event,viewport=nil,map=nil,filename=nil)
    @light = IconSprite.new(0,0,viewport)
    if filename!=nil && filename!="" && pbResolveBitmap("Graphics/Pictures/"+filename)
      @light.setBitmap("Graphics/Pictures/"+filename)
    else
      @light.setBitmap("Graphics/Pictures/LE")
    end
    @light.z = 1000
    @event = event
    @map = (map) ? map : $game_map
    @disposed = false
  end

  def disposed?
    return @disposed
  end

  def dispose
    @light.dispose
    @map = nil
    @event = nil
    @disposed = true
  end

  def update
    @light.update
  end
end



class LightEffect_Lamp < LightEffect
  def initialize(event,viewport=nil,map=nil)
    lamp = AnimatedBitmap.new("Graphics/Pictures/LE")
    @light = Sprite.new(viewport)
    @light.bitmap  = Bitmap.new(128,64)
    src_rect = Rect.new(0, 0, 64, 64) 
    @light.bitmap.blt(0, 0, lamp.bitmap, src_rect) 
    @light.bitmap.blt(20, 0, lamp.bitmap, src_rect) 
    @light.visible = true
    @light.z       = 1000
    lamp.dispose
    @map = (map) ? map : $game_map
    @event = event
  end
end



class LightEffect_Basic < LightEffect
  def update
    return if !@light || !@event
    super
    @light.opacity = 100
    @light.ox      = 32
    @light.oy      = 48
    if (Object.const_defined?(:ScreenPosHelper) rescue false)
      @light.x      = ScreenPosHelper.pbScreenX(@event)
      @light.y      = ScreenPosHelper.pbScreenY(@event)
      @light.zoom_x = ScreenPosHelper.pbScreenZoomX(@event)
    else
      @light.x      = @event.screen_x
      @light.y      = @event.screen_y
      @light.zoom_x = 1.0
    end
    @light.zoom_y = @light.zoom_x
    @light.tone   = $game_screen.tone
  end
end



class LightEffect_DayNight < LightEffect
  def update
    return if !@light || !@event
    super
    shade = PBDayNight.getShade
    if shade>=144   # If light enough, call it fully day
      shade = 255
    elsif shade<=64   # If dark enough, call it fully night
      shade = 0
    else
      shade = 255-(255*(144-shade)/(144-64))
    end
    @light.opacity = 255-shade
    if @light.opacity>0
      @light.ox = 32
      @light.oy = 48
      if (Object.const_defined?(:ScreenPosHelper) rescue false)
        @light.x      = ScreenPosHelper.pbScreenX(@event)
        @light.y      = ScreenPosHelper.pbScreenY(@event)
        @light.zoom_x = ScreenPosHelper.pbScreenZoomX(@event)
        @light.zoom_y = ScreenPosHelper.pbScreenZoomY(@event)
      else
        @light.x      = @event.screen_x
        @light.y      = @event.screen_y
        @light.zoom_x = 1.0
        @light.zoom_y = 1.0
      end
      @light.tone.set($game_screen.tone.red,
                      $game_screen.tone.green,
                      $game_screen.tone.blue,
                      $game_screen.tone.gray)
    end
  end  
end



Events.onSpritesetCreate+=proc{|sender,e|
  spriteset = e[0] # Spriteset being created
  viewport  = e[1] # Viewport used for tilemap and characters
  map = spriteset.map # Map associated with the spriteset (not necessarily the current map).
  for i in map.events.keys
    if map.events[i].name[/^OutdoorLight\((\w+)\)$/]
      filename = $~[1].to_s
      spriteset.addUserSprite(LightEffect_DayNight.new(map.events[i],viewport,map,filename))
    elsif map.events[i].name=="OutdoorLight"
      spriteset.addUserSprite(LightEffect_DayNight.new(map.events[i],viewport,map))
    elsif map.events[i].name[/^Light\((\w+)\)$/]
      filename = $~[1].to_s
      spriteset.addUserSprite(LightEffect_Basic.new(map.events[i],viewport,map,filename))
    elsif map.events[i].name=="Light"
      spriteset.addUserSprite(LightEffect_Basic.new(map.events[i],viewport,map))
    end
  end
  spriteset.addUserSprite(Particle_Engine.new(viewport,map))
}



#===============================================================================
# Battle start animation
#===============================================================================
class Game_Temp
  attr_accessor :background_bitmap
end



def pbNewBattleScene
  return PokeBattle_Scene.new
end

def pbSceneStandby
  $scene.disposeSpritesets if $scene && $scene.is_a?(Scene_Map)
  GC.start
  Graphics.frame_reset
  yield
  $scene.createSpritesets if $scene && $scene.is_a?(Scene_Map)
end

def pbBattleAnimation(bgm=nil,battletype=0,foe=nil)
  $game_temp.in_battle = true
  handled = false
  viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
  viewport.z = 99999
  # Set up audio
  playingBGS = nil
  playingBGM = nil
  if $game_system && $game_system.is_a?(Game_System)
    playingBGS = $game_system.getPlayingBGS
    playingBGM = $game_system.getPlayingBGM
    $game_system.bgm_pause
    $game_system.bgs_pause
  end
  pbMEFade(0.25)
  pbWait(10)
  pbMEStop
  # Play battle music
  bgm = pbGetWildBattleBGM(0) if !bgm
  pbBGMPlay(bgm)
  # Take screenshot of game, for use in some animations
  $game_temp.background_bitmap.dispose if $game_temp.background_bitmap
  $game_temp.background_bitmap = Graphics.snap_to_bitmap
  # Check for custom battle intro animations
  handled = pbBattleAnimationOverride(viewport,battletype,foe)
  # Default battle intro animation
  if !handled
    # Determine which animation is played
    location = 0   # 0=outside, 1=inside, 2=cave, 3=water
    if $PokemonGlobal && ($PokemonGlobal.surfing || $PokemonGlobal.diving)
      location = 3
    elsif $PokemonTemp.encounterType &&
       ($PokemonTemp.encounterType==EncounterTypes::OldRod ||
       $PokemonTemp.encounterType==EncounterTypes::GoodRod ||
       $PokemonTemp.encounterType==EncounterTypes::SuperRod)
      location = 3
    elsif $PokemonEncounters && $PokemonEncounters.isCave?
      location = 2
    elsif !pbGetMetadata($game_map.map_id,MetadataOutdoor)
      location = 1
    end
    anim = ""
    if PBDayNight.isDay?
      case battletype
      when 0, 2 # Wild, double wild
        anim = ["SnakeSquares","DiagonalBubbleTL","DiagonalBubbleBR","RisingSplash"][location]
      when 1 # Trainer
        anim = ["TwoBallPass","ThreeBallDown","BallDown","WavyThreeBallUp"][location]
      when 3 # Double trainer
        anim = "FourBallBurst"
      end
    else
      case battletype
      when 0, 2 # Wild, double wild
        anim = ["SnakeSquares","DiagonalBubbleBR","DiagonalBubbleBR","RisingSplash"][location]
      when 1 # Trainer
        anim = ["SpinBallSplit","BallDown","BallDown","WavySpinBall"][location]
      when 3 # Double trainer
        anim = "FourBallBurst"
      end
    end
    # Initial screen flashing
    if location==2 || PBDayNight.isNight?
      viewport.color = Color.new(0,0,0)         # Fade to black a few times
    else
      viewport.color = Color.new(255,255,255)   # Fade to white a few times
    end
    2.times do
      viewport.color.alpha = 0
      mult = 1
      16.times do
        viewport.color.alpha += 32*mult
        mult *= -1 if viewport.color.alpha>=255 || viewport.color.alpha<=0
        Graphics.update
        pbUpdateSceneMap
      end
    end
    # Play main animation
    Graphics.freeze
    Graphics.transition(Graphics.frame_rate*1.25,sprintf("Graphics/Transitions/%s",anim))
    viewport.color = Color.new(0,0,0,255)   # Ensure screen is black
    # Slight pause after animation before starting up the battle scene
    5.times do
      Graphics.update
      Input.update
      pbUpdateSceneMap
    end
  end
  pbPushFade
  # Yield to the battle scene
  yield if block_given?
  # After the battle
  pbPopFade
  if $game_system && $game_system.is_a?(Game_System)
    $game_system.bgm_resume(playingBGM)
    $game_system.bgs_resume(playingBGS)
  end
  $PokemonGlobal.nextBattleBGM  = nil
  $PokemonGlobal.nextBattleME   = nil
  $PokemonGlobal.nextBattleBack = nil
  $PokemonEncounters.clearStepCount
  for j in 0..17
    viewport.color = Color.new(0,0,0,(17-j)*15)
    Graphics.update
    Input.update
    pbUpdateSceneMap
  end
  viewport.dispose
  $game_temp.in_battle = false
end

def pbBattleAnimationOverride(viewport,battletype=0,foe=nil)
  ##### VS. animation, by Luka S.J. #####
  ##### Tweaked by Maruno           #####
  if (battletype==1 || battletype==3) && foe.length==1   # Against single trainer
    trainerid = (foe[0][0].trainertype rescue -1)
    if trainerid>=0
      tbargraphic = sprintf("Graphics/Transitions/vsBar%s",getConstantName(PBTrainers,trainerid)) rescue nil
      tbargraphic = sprintf("Graphics/Transitions/vsBar%d",trainerid) if !pbResolveBitmap(tbargraphic)
      tgraphic    = sprintf("Graphics/Transitions/vsTrainer%s",getConstantName(PBTrainers,trainerid)) rescue nil
      tgraphic    = sprintf("Graphics/Transitions/vsTrainer%d",trainerid) if !pbResolveBitmap(tgraphic)
      if pbResolveBitmap(tbargraphic) && pbResolveBitmap(tgraphic)
        outfit = ($Trainer) ? $Trainer.outfit : 0
        # Set up
        viewplayer = Viewport.new(0,Graphics.height/3,Graphics.width/2,128)
        viewplayer.z = viewport.z
        viewopp = Viewport.new(Graphics.width/2,Graphics.height/3,Graphics.width/2,128)
        viewopp.z = viewport.z
        viewvs = Viewport.new(0,0,Graphics.width,Graphics.height)
        viewvs.z = viewport.z
        fade = Sprite.new(viewport)
        fade.bitmap  = BitmapCache.load_bitmap("Graphics/Transitions/vsFlash")
        fade.tone    = Tone.new(-255,-255,-255)
        fade.opacity = 100
        overlay = Sprite.new(viewport)
        overlay.bitmap = Bitmap.new(Graphics.width,Graphics.height)
        pbSetSystemFont(overlay.bitmap)
        pbargraphic = sprintf("Graphics/Transitions/vsBar%s_%d",getConstantName(PBTrainers,$Trainer.trainertype),outfit) rescue nil
        pbargraphic = sprintf("Graphics/Transitions/vsBar%d_%d",$Trainer.trainertype,outfit) if !pbResolveBitmap(pbargraphic)
        if !pbResolveBitmap(pbargraphic)
          pbargraphic = sprintf("Graphics/Transitions/vsBar%s",getConstantName(PBTrainers,$Trainer.trainertype)) rescue nil
        end
        pbargraphic = sprintf("Graphics/Transitions/vsBar%d",$Trainer.trainertype) if !pbResolveBitmap(pbargraphic)
        xoffset = (((Graphics.width/2)/10).round)*10
        bar1 = Sprite.new(viewplayer)
        bar1.bitmap = BitmapCache.load_bitmap(pbargraphic)
        bar1.x      = -xoffset
        bar2 = Sprite.new(viewopp)
        bar2.bitmap = BitmapCache.load_bitmap(tbargraphic)
        bar2.x      = xoffset
        vs = Sprite.new(viewvs)
        vs.bitmap  = BitmapCache.load_bitmap("Graphics/Transitions/vs")
        vs.ox      = vs.bitmap.width/2
        vs.oy      = vs.bitmap.height/2
        vs.x       = Graphics.width/2
        vs.y       = Graphics.height/1.5
        vs.visible = false
        flash = Sprite.new(viewvs)
        flash.bitmap  = BitmapCache.load_bitmap("Graphics/Transitions/vsFlash")
        flash.opacity = 0
        # Animation
        10.times do
          bar1.x += xoffset/10
          bar2.x -= xoffset/10
          pbWait(1)
        end
        pbSEPlay("Vs flash")
        pbSEPlay("Vs sword")
        flash.opacity = 255
        bar1.dispose
        bar2.dispose
        bar1 = AnimatedPlane.new(viewplayer)
        bar1.bitmap = BitmapCache.load_bitmap(pbargraphic)
        bar2 = AnimatedPlane.new(viewopp)
        bar2.bitmap = BitmapCache.load_bitmap(tbargraphic)
        pgraphic = sprintf("Graphics/Transitions/vsTrainer%s_%d",getConstantName(PBTrainers,$Trainer.trainertype),outfit) rescue nil
        pgraphic = sprintf("Graphics/Transitions/vsTrainer%d_%d",$Trainer.trainertype,outfit) if !pbResolveBitmap(pgraphic)
        if !pbResolveBitmap(pgraphic)
          pgraphic = sprintf("Graphics/Transitions/vsTrainer%s",getConstantName(PBTrainers,$Trainer.trainertype)) rescue nil
        end
        pgraphic = sprintf("Graphics/Transitions/vsTrainer%d",$Trainer.trainertype) if !pbResolveBitmap(pgraphic)
        player = Sprite.new(viewplayer)
        player.bitmap = BitmapCache.load_bitmap(pgraphic)
        player.x      = -xoffset
        trainer = Sprite.new(viewopp)
        trainer.bitmap = BitmapCache.load_bitmap(tgraphic)
        trainer.x      = xoffset
        trainer.tone   = Tone.new(-255,-255,-255)
        25.times do
          flash.opacity -= 51 if flash.opacity>0
          bar1.ox -= 16
          bar2.ox += 16
          pbWait(1)
        end
        11.times do
          bar1.ox -= 16
          bar2.ox += 16
          player.x += xoffset/10
          trainer.x -= xoffset/10
          pbWait(1)
        end
        2.times do
          bar1.ox -= 16
          bar2.ox += 16
          player.x -= xoffset/20
          trainer.x += xoffset/20
          pbWait(1)
        end
        10.times do
          bar1.ox -= 16
          bar2.ox += 16
          pbWait(1)
        end
        val = 2
        flash.opacity = 255
        vs.visible = true
        trainer.tone = Tone.new(0,0,0)
        trainername = foe[0][0].name
        textpos = [
           [$Trainer.name,Graphics.width/4,(Graphics.height/1.5)+10,2,
              Color.new(248,248,248),Color.new(12*6,12*6,12*6)],
           [trainername,(Graphics.width/4)+(Graphics.width/2),(Graphics.height/1.5)+10,2,
              Color.new(248,248,248),Color.new(12*6,12*6,12*6)]
        ]
        pbDrawTextPositions(overlay.bitmap,textpos)
        pbSEPlay("Vs sword")
        70.times do
          bar1.ox -= 16
          bar2.ox += 16
          flash.opacity -= 25.5 if flash.opacity>0
          vs.x += val
          vs.y -= val
          val = 2 if vs.x<=(Graphics.width/2)-2
          val = -2 if vs.x>=(Graphics.width/2)+2
          pbWait(1)
        end
        30.times do
          bar1.ox -= 16
          bar2.ox += 16
          vs.zoom_x += 0.2
          vs.zoom_y += 0.2
          pbWait(1)
        end
        flash.tone = Tone.new(-255,-255,-255)
        10.times do
          bar1.ox -= 16
          bar2.ox += 16
          flash.opacity += 25.5
          pbWait(1)
        end
        # End
        player.dispose
        trainer.dispose
        flash.dispose
        vs.dispose
        bar1.dispose
        bar2.dispose
        overlay.dispose
        fade.dispose
        viewvs.dispose
        viewopp.dispose
        viewplayer.dispose
        viewport.color = Color.new(0,0,0,255)
        return true
      end
    end
  end
  return false
end

# If you want to add a custom battle intro animation, copy the following alias
# line and method into a new script section. Change the name of the alias part
# ("__over1__") in your copied code in both places. Then add in your custom
# transition code in the place shown.
# Note that $game_temp.background_bitmap contains an image of the current game
# screen.
# When the custom animation has finished, the screen should have faded to black
# somehow.

alias __over1__pbBattleAnimationOverride pbBattleAnimationOverride

def pbBattleAnimationOverride(viewport,battletype=0,foe=nil)
  # The following example runs a common event that ought to do a custom
  # animation if some condition is true:
  #
  # if $game_map && $game_map.map_id==20   # If on map 20
  #   pbCommonEvent(20)
  #   return true                          # Note that the battle animation is done
  # end
  #
  # The following line needs to call the aliased method if the custom transition
  # animation was NOT shown.
  return __over1__pbBattleAnimationOverride(viewport,battletype,foe)
end


#===============================================================================
# Entering/exiting cave animations
#===============================================================================
def pbCaveEntranceEx(exiting)
  sprite = BitmapSprite.new(Graphics.width,Graphics.height)
  sprite.z = 100000
  totalBands = 15
  totalFrames = 15
  bandheight = ((Graphics.height/2)-10).to_f/totalBands
  bandwidth  = ((Graphics.width/2)-12).to_f/totalBands
  grays = []
  tbm1 = totalBands-1
  for i in 0...totalBands
    grays.push(exiting ? 0 : 255)
  end
  totalFrames.times do |j|
    x = 0
    y = 0
    rectwidth  = Graphics.width
    rectheight = Graphics.height
    for k in 0...j
      t = (255.0)/totalFrames
      if exiting
        t = 1.0-t
        t *= 1.0+((k)/totalFrames.to_f)
      else
        t *= 1.0+0.3*(((totalFrames-k)/totalFrames.to_f)**0.7)
      end
      grays[k] -= t
      grays[k] = 0 if grays[k]<0
    end
    for i in 0...totalBands
      currentGray = grays[i]
      sprite.bitmap.fill_rect(Rect.new(x,y,rectwidth,rectheight),
         Color.new(currentGray,currentGray,currentGray))
      x += bandwidth
      y += bandheight
      rectwidth  -= bandwidth*2
      rectheight -= bandheight*2
    end
    Graphics.update
    Input.update
  end
  if exiting
    pbToneChangeAll(Tone.new(255,255,255),0)
  else
    pbToneChangeAll(Tone.new(-255,-255,-255),0)
  end
  for j in 0..15
    if exiting
      sprite.color = Color.new(255,255,255,j*255/15)
    else
      sprite.color = Color.new(0,0,0,j*255/15) 
    end
    Graphics.update
    Input.update
  end
  pbToneChangeAll(Tone.new(0,0,0),8)
  for j in 0..5
    Graphics.update
    Input.update
  end
  sprite.dispose
end

def pbCaveEntrance
  pbSetEscapePoint
  pbCaveEntranceEx(false)
end

def pbCaveExit
  pbEraseEscapePoint
  pbCaveEntranceEx(true)
end



#===============================================================================
# Blacking out animation
#===============================================================================
def Kernel.pbRxdataExists?(file)
  if $RPGVX
    return pbRgssExists?(file+".rvdata")
  else
    return pbRgssExists?(file+".rxdata")
  end
end

def Kernel.pbStartOver(gameover=false)
  if pbInBugContest?
    Kernel.pbBugContestStartOver
    return
  end
  pbHealAll
  if $PokemonGlobal.pokecenterMapId && $PokemonGlobal.pokecenterMapId>=0
    if gameover
      Kernel.pbMessage(_INTL("\\w[]\\wm\\c[8]\\l[3]After the unfortunate defeat, you scurry back to a Pokémon Center."))
    else
      Kernel.pbMessage(_INTL("\\w[]\\wm\\c[8]\\l[3]You scurry back to a Pokémon Center, protecting your exhausted Pokémon from any further harm..."))
    end
    Kernel.pbCancelVehicles
    pbRemoveDependencies
    $game_switches[STARTING_OVER_SWITCH] = true
    $game_temp.player_new_map_id    = $PokemonGlobal.pokecenterMapId
    $game_temp.player_new_x         = $PokemonGlobal.pokecenterX
    $game_temp.player_new_y         = $PokemonGlobal.pokecenterY
    $game_temp.player_new_direction = $PokemonGlobal.pokecenterDirection
    $scene.transfer_player if $scene.is_a?(Scene_Map)
    $game_map.refresh
  else
    homedata = pbGetMetadata(0,MetadataHome)
    if homedata && !pbRxdataExists?(sprintf("Data/Map%03d",homedata[0]))
      if $DEBUG
        Kernel.pbMessage(_ISPRINTF("Can't find the map 'Map{1:03d}' in the Data folder. The game will resume at the player's position.",homedata[0]))
      end
      pbHealAll
      return
    end
    if gameover
      Kernel.pbMessage(_INTL("\\w[]\\wm\\c[8]\\l[3]After the unfortunate defeat, you scurry back home."))
    else
      Kernel.pbMessage(_INTL("\\w[]\\wm\\c[8]\\l[3]You scurry back home, protecting your exhausted Pokémon from any further harm..."))
    end
    if homedata
      Kernel.pbCancelVehicles
      pbRemoveDependencies
      $game_switches[STARTING_OVER_SWITCH] = true
      $game_temp.player_new_map_id    = homedata[0]
      $game_temp.player_new_x         = homedata[1]
      $game_temp.player_new_y         = homedata[2]
      $game_temp.player_new_direction = homedata[3]
      $scene.transfer_player if $scene.is_a?(Scene_Map)
      $game_map.refresh
    else
      pbHealAll
    end
  end
  pbEraseEscapePoint
end



#===============================================================================
# Various other screen effects
#===============================================================================
def pbToneChangeAll(tone,duration)
  $game_screen.start_tone_change(tone,duration*2)
  for picture in $game_screen.pictures
    picture.start_tone_change(tone,duration*2) if picture
  end
end

def pbShake(power,speed,frames)
  $game_screen.start_shake(power,speed,frames*2)
end

def pbFlash(color,frames)
  $game_screen.start_flash(color,frames*2)
end

def pbScrollMap(direction,distance,speed)
  return if !$game_map
  if speed==0
    case direction
    when 2; $game_map.scroll_down(distance * 128)
    when 4; $game_map.scroll_left(distance * 128)
    when 6; $game_map.scroll_right(distance * 128)
    when 8; $game_map.scroll_up(distance * 128)
    end
  else
    $game_map.start_scroll(direction, distance, speed);
    oldx = $game_map.display_x
    oldy = $game_map.display_y
    loop do
      Graphics.update
      Input.update
      break if !$game_map.scrolling?
      pbUpdateSceneMap
      break if $game_map.display_x==oldx && $game_map.display_y==oldy
      oldx = $game_map.display_x
      oldy = $game_map.display_y 
    end
  end
end