class Game_Player
  @@bobframespeed = 1.0/15

  def fullPattern
    case self.direction
    when 2; return self.pattern
    when 4; return 4+self.pattern
    when 6; return 8+self.pattern
    when 8; return 12+self.pattern
    end
    return 0
  end

  def setDefaultCharName(chname,pattern,lockpattern=false)
    return if pattern<0 || pattern>=16
    @defaultCharacterName = chname
    @direction = [2,4,6,8][pattern/4]
    @pattern = pattern%4
    @lock_pattern = lockpattern
  end

  def pbCanRun?
    return false if $game_temp.in_menu || $game_temp.in_battle ||
                    @move_route_forcing || $game_temp.message_window_showing ||
                    pbMapInterpreterRunning?
    terrain = pbGetTerrainTag
    input = ($PokemonSystem.runstyle==1) ? ($PokemonGlobal && $PokemonGlobal.runtoggle) : Input.press?(Input::A)
    return input &&
       $PokemonGlobal && $PokemonGlobal.runningShoes &&
       !$PokemonGlobal.diving && !$PokemonGlobal.surfing &&
       !$PokemonGlobal.bicycle && !PBTerrain.onlyWalk?(terrain)
  end

  def pbIsRunning?
    return moving? && !@move_route_forcing && $PokemonGlobal && pbCanRun?
  end

  def character_name
    @defaultCharacterName = "" if !@defaultCharacterName
    return @defaultCharacterName if @defaultCharacterName!=""
    if !@move_route_forcing && $PokemonGlobal && $PokemonGlobal.playerID>=0
      meta = pbGetMetadata(0,MetadataPlayerA+$PokemonGlobal.playerID)
      if meta && !$PokemonGlobal.bicycle && !$PokemonGlobal.diving && !$PokemonGlobal.surfing
        if pbCanRun? && (moving? || @wasmoving) && Input.dir4!=0 && meta[4] && meta[4]!=""
          # Display running character sprite
          @character_name = pbGetPlayerCharset(meta,4)
        else
          # Display normal character sprite 
          @character_name = pbGetPlayerCharset(meta,1)
        end
        @wasmoving = moving?
      end
    end
    return @character_name
  end

  alias update_old update

  def update
    if PBTerrain.isIce?(pbGetTerrainTag)
      @move_speed = ($RPGVX) ? 6.5 : 4.8 # Sliding on ice
    elsif !moving? && !@move_route_forcing && $PokemonGlobal
      if $PokemonGlobal.bicycle
        @move_speed = ($RPGVX) ? 8 : 5.2 # Cycling
      elsif pbCanRun? || $PokemonGlobal.surfing || $PokemonGlobal.diving
        @move_speed = ($RPGVX) ? 6.5 : 4.8 # Running, surfing or diving
      else
        @move_speed = ($RPGVX) ? 4.5 : 3.8 # Walking
      end
    end
    update_old
  end

  def update_pattern
    if $PokemonGlobal.surfing || $PokemonGlobal.diving
      p = ((Graphics.frame_count%60)*@@bobframespeed).floor
      @pattern = p if !@lock_pattern
      @pattern_surf = p
      @bob_height = (p>=2) ? 2 : 0
    else
      super
    end
  end
end


=begin
class Game_Character
  alias update_old2 update

  def update
    if self.is_a?(Game_Event)
      if @dependentEvents
        for i in 0...@dependentEvents.length
          if @dependentEvents[i][0]==$game_map.map_id &&
             @dependentEvents[i][1]==self.id
            @move_speed = $game_player.move_speed
            break
          end
        end
      end
    end
    update_old2
  end
end
=end