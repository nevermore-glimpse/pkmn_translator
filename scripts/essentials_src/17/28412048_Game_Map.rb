#==============================================================================
# ** Game_Map
#------------------------------------------------------------------------------
#  This class handles the map. It includes scrolling and passable determining
#  functions. Refer to "$game_map" for the instance of this class.
#==============================================================================

class Game_Map
  attr_accessor :map_id
  attr_accessor :tileset_name             # tileset file name
  attr_accessor :autotile_names           # autotile file name
  attr_reader   :passages                 # passage table
  attr_reader   :priorities               # prioroty table
  attr_reader   :terrain_tags             # terrain tag table
  attr_reader   :events                   # events
  attr_accessor :panorama_name            # panorama file name
  attr_accessor :panorama_hue             # panorama hue
  attr_accessor :fog_name                 # fog file name
  attr_accessor :fog_hue                  # fog hue
  attr_accessor :fog_opacity              # fog opacity level
  attr_accessor :fog_blend_type           # fog blending method
  attr_accessor :fog_zoom                 # fog zoom rate
  attr_accessor :fog_sx                   # fog sx
  attr_accessor :fog_sy                   # fog sy
  attr_reader   :fog_ox                   # fog x-coordinate starting point
  attr_reader   :fog_oy                   # fog y-coordinate starting point
  attr_reader   :fog_tone                 # fog color tone
  attr_accessor :battleback_name          # battleback file name
  attr_accessor :display_x                # display x-coordinate * 128
  attr_accessor :display_y                # display y-coordinate * 128
  attr_accessor :need_refresh             # refresh request flag

  def initialize
    @map_id = 0
    @display_x = 0
    @display_y = 0
  end

  def setup(map_id)
    @map_id = map_id
    @map = load_data(sprintf("Data/Map%03d.%s",map_id,($RPGVX) ? "rvdata" : "rxdata"))
    tileset = $data_tilesets[@map.tileset_id]
    updateTileset
    @fog_ox = 0
    @fog_oy = 0
    @fog_tone = Tone.new(0, 0, 0, 0)
    @fog_tone_target = Tone.new(0, 0, 0, 0)
    @fog_tone_duration = 0
    @fog_opacity_duration = 0
    @fog_opacity_target = 0
    self.display_x = 0
    self.display_y = 0
    @need_refresh = false
    Events.onMapCreate.trigger(self,map_id,@map,tileset)
    @events = {}
    for i in @map.events.keys
      @events[i] = Game_Event.new(@map_id, @map.events[i],self)
    end
    @common_events = {}
    for i in 1...$data_common_events.size
      @common_events[i] = Game_CommonEvent.new(i)
    end
    @scroll_direction = 2
    @scroll_rest = 0
    @scroll_speed = 4
  end

  def updateTileset
    tileset = $data_tilesets[@map.tileset_id]
    @tileset_name    = tileset.tileset_name
    @autotile_names  = tileset.autotile_names
    @panorama_name   = tileset.panorama_name
    @panorama_hue    = tileset.panorama_hue
    @fog_name        = tileset.fog_name
    @fog_hue         = tileset.fog_hue
    @fog_opacity     = tileset.fog_opacity
    @fog_blend_type  = tileset.fog_blend_type
    @fog_zoom        = tileset.fog_zoom
    @fog_sx          = tileset.fog_sx
    @fog_sy          = tileset.fog_sy
    @battleback_name = tileset.battleback_name
    @passages        = tileset.passages
    @priorities      = tileset.priorities
    @terrain_tags    = tileset.terrain_tags
  end

  def width; return @map.width; end
  def height; return @map.height; end
  def encounter_list; return @map.encounter_list; end
  def encounter_step; return @map.encounter_step; end
  def data; return @map.data; end

  def name
    ret=pbGetMessage(MessageTypes::MapNames,@map_id)
    ret.gsub!(/\\PN/,$Trainer.name) if $Trainer
    return ret
  end
  #-----------------------------------------------------------------------------
  # * Autoplays background music
  #   Plays music called "[normal BGM]n" if it's night time and it exists
  #-----------------------------------------------------------------------------
  def autoplayAsCue
    if @map.autoplay_bgm
      if PBDayNight.isNight? && FileTest.audio_exist?("Audio/BGM/"+ @map.bgm.name+ "n")
        pbCueBGM(@map.bgm.name+"n",1.0,@map.bgm.volume,@map.bgm.pitch)
      else
        pbCueBGM(@map.bgm,1.0)
      end
    end
    if @map.autoplay_bgs
      pbBGSPlay(@map.bgs)
    end
  end
  #-----------------------------------------------------------------------------
  # * Plays background music
  #   Plays music called "[normal BGM]n" if it's night time and it exists
  #-----------------------------------------------------------------------------
  def autoplay
    if @map.autoplay_bgm
      if PBDayNight.isNight? && FileTest.audio_exist?("Audio/BGM/"+ @map.bgm.name+ "n")
        pbBGMPlay(@map.bgm.name+"n",@map.bgm.volume,@map.bgm.pitch)
      else
        pbBGMPlay(@map.bgm)
      end
    end
    if @map.autoplay_bgs
      pbBGSPlay(@map.bgs)
    end
  end

  def valid?(x, y)
     return (x>=0 and x<width and y>=0 and y<height)
  end

  def validLax?(x, y)
    return (x>=-10 and x<=width+10 and y>=-10 and y<=height+10)
  end

  def in_range?(object)
    return true if $PokemonSystem.tilemap==2
    screne_x = display_x - 4*32*4
    screne_y = display_y - 4*32*4
    screne_width  = display_x + Graphics.width*4 + 4*32*4
    screne_height = display_y + Graphics.height*4 + 4*32*4
    return false if object.real_x <= screne_x || object.real_x >= screne_width
    return false if object.real_y <= screne_y || object.real_y >= screne_height
    return true
  end

  def passable?(x, y, d, self_event = nil)
    return false if !valid?(x, y)
    bit = (1 << (d / 2 - 1)) & 0x0f
    for event in events.values
      if event.tile_id >= 0 and event != self_event and
         event.x == x and event.y == y and not event.through
        if @terrain_tags[event.tile_id]!=PBTerrain::Neutral
          return false if @passages[event.tile_id] & bit != 0
          return false if @passages[event.tile_id] & 0x0f == 0x0f
          return true if @priorities[event.tile_id] == 0
        end
      end
    end
    if self_event==$game_player
      return playerPassable?(x, y, d, self_event)
    else
      # All other events
      newx = x; newy = y
      case d
      when 1; newx -= 1; newy += 1
      when 2; newy += 1
      when 3; newx += 1; newy += 1
      when 4; newx -= 1
      when 6; newx += 1
      when 7; newx -= 1; newy -= 1
      when 8; newy -= 1
      when 9; newx += 1; newy -= 1
      end
      return false if !valid?(newx, newy)
      for i in [2, 1, 0]
        tile_id = data[x, y, i]
        if tile_id == nil
          return false
        # If already on water, only allow movement to another water tile
        elsif self_event!=nil &&
           PBTerrain.isJustWater?(@terrain_tags[tile_id])
          for j in [2, 1, 0]
            facing_tile_id=data[newx, newy, j]
            return false if facing_tile_id==nil
            if @terrain_tags[facing_tile_id]!=0 &&
               @terrain_tags[facing_tile_id]!=PBTerrain::Neutral
              return PBTerrain.isJustWater?(@terrain_tags[facing_tile_id])
            end
          end
          return false
        # Can't walk onto ice
        elsif PBTerrain.isIce?(@terrain_tags[tile_id])
          return false
        elsif self_event!=nil && self_event.x==x && self_event.y==y
          # Can't walk onto ledges
          for j in [2, 1, 0]
            facing_tile_id=data[newx, newy, j]
            return false if facing_tile_id==nil
            if @terrain_tags[facing_tile_id]!=0 &&
               @terrain_tags[facing_tile_id]!=PBTerrain::Neutral
              return false if PBTerrain.isLedge?(@terrain_tags[facing_tile_id])
              break
            end
          end
          # Regular passability checks
          if @terrain_tags[tile_id]!=PBTerrain::Neutral
            if @passages[tile_id] & bit != 0 ||
               @passages[tile_id] & 0x0f == 0x0f
              return false
            elsif @priorities[tile_id] == 0
              return true
            end
          end
        # Regular passability checks
        elsif @terrain_tags[tile_id]!=PBTerrain::Neutral
          if @passages[tile_id] & bit != 0 ||
             @passages[tile_id] & 0x0f == 0x0f
            return false
          elsif @priorities[tile_id] == 0
            return true
          end
        end
      end
      return true
    end
  end

  def playerPassable?(x, y, d, self_event = nil)
    bit = (1 << (d / 2 - 1)) & 0x0f
    for i in [2, 1, 0]
      tile_id = data[x, y, i]
      # Ignore bridge tiles if not on a bridge
      next if $PokemonGlobal && $PokemonGlobal.bridge==0 &&
         tile_id && PBTerrain.isBridge?(@terrain_tags[tile_id])
      if tile_id == nil
        return false
      # Make water tiles passable if player is surfing
      elsif $PokemonGlobal.surfing &&
         PBTerrain.isPassableWater?(@terrain_tags[tile_id])
        return true
      # Prevent cycling in really tall grass/on ice
      elsif $PokemonGlobal.bicycle &&
         PBTerrain.onlyWalk?(@terrain_tags[tile_id])
        return false
      # Depend on passability of bridge tile if on bridge
      elsif $PokemonGlobal && $PokemonGlobal.bridge>0 &&
         PBTerrain.isBridge?(@terrain_tags[tile_id])
        if @passages[tile_id] & bit != 0 ||
           @passages[tile_id] & 0x0f == 0x0f
          return false
        else
          return true
        end
      # Regular passability checks
      elsif @terrain_tags[tile_id]!=PBTerrain::Neutral
        if @passages[tile_id] & bit != 0 ||
           @passages[tile_id] & 0x0f == 0x0f
          return false
        elsif @priorities[tile_id] == 0
          return true
        end
      end
    end
    return true
  end

  def passableStrict?(x, y, d, self_event = nil)
    return false if !valid?(x, y)
    for event in events.values
      if event.tile_id >= 0 and event != self_event and
         event.x == x and event.y == y and not event.through
        if @terrain_tags[event.tile_id]!=PBTerrain::Neutral
          return false if @passages[event.tile_id] & 0x0f != 0
          return true if @priorities[event.tile_id] == 0
        end
      end
    end
    for i in [2, 1, 0]
      tile_id = data[x, y, i]
      return false if tile_id == nil
      if @terrain_tags[tile_id]!=PBTerrain::Neutral
        return false if @passages[tile_id] & 0x0f != 0
        return true if @priorities[tile_id] == 0
      end
    end
    return true
  end

  def deepBush?(x,y)
    if @map_id != 0
      for i in [2, 1, 0]
        tile_id = data[x, y, i]
        if tile_id == nil
          return false
        elsif PBTerrain.isBridge?(@terrain_tags[tile_id]) && $PokemonGlobal &&
              $PokemonGlobal.bridge>0
          return false
        elsif @passages[tile_id] & 0x40 == 0x40 &&
           @terrain_tags[tile_id]==PBTerrain::TallGrass
          return true
        end
      end
    end
    return false
  end

  def bush?(x,y)
    if @map_id != 0
      for i in [2, 1, 0]
        tile_id = data[x, y, i]
        if tile_id == nil
          return false
        elsif PBTerrain.isBridge?(@terrain_tags[tile_id]) && $PokemonGlobal &&
              $PokemonGlobal.bridge>0
          return false
        elsif @passages[tile_id] & 0x40 == 0x40
          return true
        end
      end
    end
    return false
  end

  def counter?(x,y)
    if @map_id != 0
      for i in [2, 1, 0]
        tile_id = data[x, y, i]
        if tile_id == nil
          return false
        elsif @passages[tile_id] && @passages[tile_id] & 0x80 == 0x80
          return true
        end
      end
    end
    return false
  end

  def terrain_tag(x,y,countBridge=false)
    if @map_id != 0
      for i in [2, 1, 0]
        tile_id = data[x, y, i]
        next if tile_id && PBTerrain.isBridge?(@terrain_tags[tile_id]) &&
                $PokemonGlobal && $PokemonGlobal.bridge==0 && !countBridge
        if tile_id == nil
          return 0
        elsif @terrain_tags[tile_id] && @terrain_tags[tile_id] > 0 &&
           @terrain_tags[tile_id]!=PBTerrain::Neutral
          return @terrain_tags[tile_id]
        end
      end
    end
    return 0
  end

  def check_event(x,y)
    for event in self.events.values
      return event.id if event.x == x and event.y == y
    end
  end

  def scroll_down(distance)
    @display_y = [@display_y+distance,(self.height-15)*128].min
  end

  def scroll_left(distance)
    @display_x = [@display_x-distance,0].max
  end

  def scroll_right(distance)
    @display_x = [@display_x+distance,(self.width-20)*128].min
  end

  def scroll_up(distance)
    @display_y = [@display_y-distance,0].max
  end

  def start_scroll(direction,distance,speed)
    @scroll_direction = direction
    @scroll_rest = distance*128
    @scroll_speed = speed
  end

  def scrolling?
    return @scroll_rest > 0
  end

  def start_fog_tone_change(tone,duration)
    @fog_tone_target = tone.clone
    @fog_tone_duration = duration
    if @fog_tone_duration == 0
      @fog_tone = @fog_tone_target.clone
    end
  end

  def start_fog_opacity_change(opacity,duration)
    @fog_opacity_target = opacity*1.0
    @fog_opacity_duration = duration
    if @fog_opacity_duration==0
      @fog_opacity = @fog_opacity_target
    end
  end

  def refresh
    if @map_id>0
      for event in @events.values
        event.refresh
      end
      for common_event in @common_events.values
        common_event.refresh
      end
    end
    @need_refresh = false
  end

  def update
    # refresh maps if necessary
    if $MapFactory
      for i in $MapFactory.maps
        i.refresh if i.need_refresh
      end
      $MapFactory.setCurrentMap
    end
    # If scrolling
    if @scroll_rest>0
      distance = 2**@scroll_speed
      case @scroll_direction
      when 2; scroll_down(distance)
      when 4; scroll_left(distance)
      when 6; scroll_right(distance)
      when 8; scroll_up(distance)
      end
      @scroll_rest -= distance
    end
    # Only update events that are on-screen
    for event in @events.values
      if in_range?(event) or event.move_route_forcing or
         event.trigger==3 or event.trigger==4
        event.update
      end
    end
    # Update common events
    for common_event in @common_events.values
      common_event.update
    end
    # Update fog
    @fog_ox -= @fog_sx/8.0
    @fog_oy -= @fog_sy/8.0
    if @fog_tone_duration>=1
      d = @fog_tone_duration
      target = @fog_tone_target
      @fog_tone.red   = (@fog_tone.red * (d - 1) + target.red) / d
      @fog_tone.green = (@fog_tone.green * (d - 1) + target.green) / d
      @fog_tone.blue  = (@fog_tone.blue * (d - 1) + target.blue) / d
      @fog_tone.gray  = (@fog_tone.gray * (d - 1) + target.gray) / d
      @fog_tone_duration -= 1
    end
    if @fog_opacity_duration >= 1
      d = @fog_opacity_duration
      @fog_opacity = (@fog_opacity * (d - 1) + @fog_opacity_target) / d
      @fog_opacity_duration -= 1
    end
  end
end