#===============================================================================
# ** Modified Scene_Map class for Pokémon.
#-------------------------------------------------------------------------------
#  
#===============================================================================
class Scene_Map
  attr_reader :spritesetglobal

  def spriteset
    for i in @spritesets.values
      return i if i.map==$game_map
    end
    return @spritesets.values[0]
  end

  def createSpritesets
    @spritesetglobal=Spriteset_Global.new
    @spritesets={}
    for map in $MapFactory.maps
      @spritesets[map.map_id]=Spriteset_Map.new(map)
    end
    $MapFactory.setSceneStarted(self)
    updateSpritesets
  end

  def createSingleSpriteset(map)
    temp=$scene.spriteset.getAnimations
    @spritesets[map]=Spriteset_Map.new($MapFactory.maps[map])
    $scene.spriteset.restoreAnimations(temp)
    $MapFactory.setSceneStarted(self)
    updateSpritesets
  end

  def updateSpritesets
    @spritesets={} if !@spritesets
    keys=@spritesets.keys.clone
    for i in keys
      if !$MapFactory.hasMap?(i)
        @spritesets[i].dispose if @spritesets[i]
        @spritesets[i]=nil
        @spritesets.delete(i)
      else
        @spritesets[i].update
      end
    end
    @spritesetglobal.update
    for map in $MapFactory.maps
      @spritesets[map.map_id] = Spriteset_Map.new(map) if !@spritesets[map.map_id]
    end
    Events.onMapUpdate.trigger(self)
  end

  def disposeSpritesets
    return if !@spritesets
    for i in @spritesets.keys
      if @spritesets[i]
        @spritesets[i].dispose
        @spritesets[i]=nil
      end
    end
    @spritesets.clear
    @spritesets={}
    @spritesetglobal.dispose
    @spritesetglobal=nil
  end

  def autofade(mapid)
    playingBGM=$game_system.playing_bgm
    playingBGS=$game_system.playing_bgs
    return if !playingBGM && !playingBGS
    map=pbLoadRxData(sprintf("Data/Map%03d",mapid))
    if playingBGM && map.autoplay_bgm
      if (PBDayNight.isNight? rescue false)
        pbBGMFade(0.8) if playingBGM.name!=map.bgm.name && playingBGM.name!=map.bgm.name+"n"
      else
        pbBGMFade(0.8) if playingBGM.name!=map.bgm.name
      end
    end
    if playingBGS && map.autoplay_bgs
      pbBGMFade(0.8) if playingBGS.name!=map.bgs.name
    end
    Graphics.frame_reset
  end

  def transfer_player(cancelVehicles=true)
    $game_temp.player_transferring = false
    Kernel.pbCancelVehicles($game_temp.player_new_map_id) if cancelVehicles
    autofade($game_temp.player_new_map_id)
    pbBridgeOff
    if $game_map.map_id!=$game_temp.player_new_map_id
      $MapFactory.setup($game_temp.player_new_map_id)
    end
    $game_player.moveto($game_temp.player_new_x, $game_temp.player_new_y)
    case $game_temp.player_new_direction
    when 2; $game_player.turn_down
    when 4; $game_player.turn_left
    when 6; $game_player.turn_right
    when 8; $game_player.turn_up
    end
    $game_player.straighten
    $game_map.update
    disposeSpritesets
    GC.start
    createSpritesets
    if $game_temp.transition_processing
      $game_temp.transition_processing = false
      Graphics.transition(20)
    end
    $game_map.autoplay
    Graphics.frame_reset
    Input.update
  end

  def call_name
    $game_temp.name_calling = false
    $game_player.straighten
    $game_map.update
  end

  def call_menu
    $game_temp.menu_calling = false
    $game_temp.in_menu = true
    $game_player.straighten
    $game_map.update
    sscene=PokemonPauseMenu_Scene.new
    sscreen=PokemonPauseMenu.new(sscene) 
    sscreen.pbStartPokemonMenu
    $game_temp.in_menu = false
  end

  def call_debug
    $game_temp.debug_calling = false
    pbPlayDecisionSE()
    $game_player.straighten
    pbFadeOutIn(99999){ pbDebugMenu }
  end

  def updateMaps
    for map in $MapFactory.maps
      map.update
    end
    $MapFactory.updateMaps(self)
  end

  def miniupdate
    $PokemonTemp.miniupdate=true if $PokemonTemp
    loop do
      updateMaps
      $game_player.update
      $game_system.update
      $game_screen.update
      break unless $game_temp.player_transferring
      transfer_player
      break if $game_temp.transition_processing
    end
    updateSpritesets
    $PokemonTemp.miniupdate=false if $PokemonTemp
  end

  def update
    loop do
      updateMaps
      pbMapInterpreter.update
      $game_player.update
      $game_system.update
      $game_screen.update
      break unless $game_temp.player_transferring
      transfer_player
      break if $game_temp.transition_processing
    end
    updateSpritesets
    if $game_temp.to_title
      $scene = pbCallTitle
      return
    end
    if $game_temp.transition_processing
      $game_temp.transition_processing = false
      if $game_temp.transition_name == ""
        Graphics.transition(20)
      else
        Graphics.transition(40, "Graphics/Transitions/" + $game_temp.transition_name)
      end
    end
    return if $game_temp.message_window_showing
    if Input.trigger?(Input::C)
      unless pbMapInterpreterRunning?
        $PokemonTemp.hiddenMoveEventCalling=true
      end
    end      
    if Input.trigger?(Input::B)
      unless pbMapInterpreterRunning? or $game_system.menu_disabled or $game_player.moving?
        $game_temp.menu_calling = true
        $game_temp.menu_beep = true
      end
    end
    if Input.trigger?(Input::F5)
      unless pbMapInterpreterRunning? or $game_player.moving?
        $PokemonTemp.keyItemCalling = true if $PokemonTemp
      end
    end
    if Input.trigger?(Input::A)
      if !pbMapInterpreterRunning? && $PokemonGlobal && $PokemonSystem && $PokemonSystem.runstyle==1
        $PokemonGlobal.runtoggle=!$PokemonGlobal.runtoggle
      end
    end
    if $DEBUG and Input.press?(Input::F9)
      $game_temp.debug_calling = true
    end
    unless $game_player.moving?
      if $game_temp.battle_calling; call_battle
      elsif $game_temp.shop_calling; call_shop
      elsif $game_temp.name_calling; call_name
      elsif $game_temp.menu_calling; call_menu
      elsif $game_temp.save_calling; call_save
      elsif $game_temp.debug_calling; call_debug
      elsif $PokemonTemp && $PokemonTemp.keyItemCalling
        $PokemonTemp.keyItemCalling=false
        $game_player.straighten
        Kernel.pbUseKeyItem
      elsif $PokemonTemp && $PokemonTemp.hiddenMoveEventCalling
        $PokemonTemp.hiddenMoveEventCalling=false
        $game_player.straighten
        Events.onAction.trigger(self)
      end
    end
  end

  def main
    createSpritesets
    Graphics.transition
    loop do
      Graphics.update
      Input.update
      update
      break if $scene != self
    end
    Graphics.freeze
    disposeSpritesets
    if $game_temp.to_title
      Graphics.transition
      Graphics.freeze
    end
  end
end