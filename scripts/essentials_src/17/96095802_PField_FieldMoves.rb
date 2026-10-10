#===============================================================================
# Hidden move handlers
#===============================================================================
class MoveHandlerHash < HandlerHash
  def initialize
    super(:PBMoves)
  end
end



module HiddenMoveHandlers
  CanUseMove     = MoveHandlerHash.new
  ConfirmUseMove = MoveHandlerHash.new
  UseMove        = MoveHandlerHash.new

  def self.addCanUseMove(item,proc); CanUseMove.add(item,proc); end
  def self.addConfirmUseMove(item,proc); ConfirmUseMove.add(item,proc); end 
  def self.addUseMove(item,proc); UseMove.add(item,proc); end 

  def self.hasHandler(item)
    return CanUseMove[item]!=nil && UseMove[item]!=nil
  end

  # Returns whether move can be used
  def self.triggerCanUseMove(item,pokemon,showmsg)
    return false if !CanUseMove[item]
    return CanUseMove.trigger(item,pokemon,showmsg)
  end

  # Returns whether the player confirmed that they want to use the move
  def self.triggerConfirmUseMove(item,pokemon)
    return true if !ConfirmUseMove[item]
    return ConfirmUseMove.trigger(item,pokemon)
  end

  # Returns whether move was used
  def self.triggerUseMove(item,pokemon)
    return false if !UseMove[item]
    return UseMove.trigger(item,pokemon)
  end
end



def Kernel.pbCanUseHiddenMove?(pkmn,move,showmsg=true)
  return HiddenMoveHandlers.triggerCanUseMove(move,pkmn,showmsg)
end

def Kernel.pbConfirmUseHiddenMove(pokemon,move)
  return HiddenMoveHandlers.triggerConfirmUseMove(move,pokemon)
end

def Kernel.pbUseHiddenMove(pokemon,move)
  return HiddenMoveHandlers.triggerUseMove(move,pokemon)
end

def Kernel.pbHiddenMoveEvent
  Events.onAction.trigger(nil)
end

def pbCheckHiddenMoveBadge(badge=-1,showmsg=true)
  return true if badge<0   # No badge requirement
  return true if $DEBUG
  if (HIDDENMOVESCOUNTBADGES) ? $Trainer.numbadges>=badge : $Trainer.badges[badge]
    return true
  end
  Kernel.pbMessage(_INTL("Sorry, a new Badge is required.")) if showmsg
  return false
end



#===============================================================================
# Hidden move animation
#===============================================================================
def pbHiddenMoveAnimation(pokemon)
  return false if !pokemon
  viewport=Viewport.new(0,0,0,0)
  viewport.z=99999
  bg=Sprite.new(viewport)
  bg.bitmap=BitmapCache.load_bitmap("Graphics/Pictures/hiddenMovebg")
  sprite=PokemonSprite.new(viewport)
  sprite.setOffset(PictureOrigin::Center)
  sprite.setPokemonBitmap(pokemon)
  sprite.z=1
  sprite.visible=false
  strobebitmap=AnimatedBitmap.new("Graphics/Pictures/hiddenMoveStrobes")
  strobes=[]
  15.times do |i|
    strobe=BitmapSprite.new(26*2,8*2,viewport)
    strobe.bitmap.blt(0,0,strobebitmap.bitmap,Rect.new(0,(i%2)*8*2,26*2,8*2))
    strobe.z=((i%2)==0 ? 2 : 0)
    strobe.visible=false
    strobes.push(strobe)
  end
  strobebitmap.dispose
  interp=RectInterpolator.new(
     Rect.new(0,Graphics.height/2,Graphics.width,0),
     Rect.new(0,(Graphics.height-bg.bitmap.height)/2,Graphics.width,bg.bitmap.height),
     10)
  ptinterp=nil
  phase=1
  frames=0
  begin
    Graphics.update
    Input.update
    sprite.update
    case phase
    when 1 # Expand viewport height from zero to full
      interp.update
      interp.set(viewport.rect)
      bg.oy=(bg.bitmap.height-viewport.rect.height)/2
      if interp.done?
        phase=2
        ptinterp=PointInterpolator.new(
           Graphics.width+(sprite.bitmap.width/2),bg.bitmap.height/2,
           Graphics.width/2,bg.bitmap.height/2,
           16)
      end
    when 2 # Slide Pokémon sprite in from right to centre
      ptinterp.update
      sprite.x=ptinterp.x
      sprite.y=ptinterp.y
      sprite.visible=true
      if ptinterp.done?
        phase=3
        pbPlayCry(pokemon)
        frames=0
      end
    when 3 # Wait
      frames+=1
      if frames>30
        phase=4
        ptinterp=PointInterpolator.new(
           Graphics.width/2,bg.bitmap.height/2,
           -(sprite.bitmap.width/2),bg.bitmap.height/2,
           16)
        frames=0
      end
    when 4 # Slide Pokémon sprite off from centre to left
      ptinterp.update
      sprite.x=ptinterp.x
      sprite.y=ptinterp.y
      if ptinterp.done?
        phase=5
        sprite.visible=false
        interp=RectInterpolator.new(
           Rect.new(0,(Graphics.height-bg.bitmap.height)/2,Graphics.width,bg.bitmap.height),
           Rect.new(0,Graphics.height/2,Graphics.width,0),
           10)
      end
    when 5 # Shrink viewport height from full to zero
      interp.update
      interp.set(viewport.rect)
      bg.oy=(bg.bitmap.height-viewport.rect.height)/2
      phase=6 if interp.done?    
    end
    for strobe in strobes
      strobe.ox=strobe.viewport.rect.x
      strobe.oy=strobe.viewport.rect.y
      if !strobe.visible
        randomY=16*(1+rand(bg.bitmap.height/16-2))
        strobe.y=randomY+(Graphics.height-bg.bitmap.height)/2
        strobe.x=rand(Graphics.width)
        strobe.visible=true
      elsif strobe.x<Graphics.width
        strobe.x+=32
      else
        randomY=16*(1+rand(bg.bitmap.height/16-2))
        strobe.y=randomY+(Graphics.height-bg.bitmap.height)/2
        strobe.x=-strobe.bitmap.width-rand(Graphics.width/4)
      end
    end
    pbUpdateSceneMap
  end while phase!=6
  sprite.dispose
  for strobe in strobes
    strobe.dispose
  end
  strobes.clear
  bg.dispose
  viewport.dispose
  return true
end



#===============================================================================
# Cut
#===============================================================================
def Kernel.pbCut
  move = getID(PBMoves,:CUT)
  movefinder = Kernel.pbCheckMove(move)
  if !pbCheckHiddenMoveBadge(BADGEFORCUT,false) || (!$DEBUG && !movefinder)
    Kernel.pbMessage(_INTL("This tree looks like it can be cut down."))
    return false
  end
  Kernel.pbMessage(_INTL("This tree looks like it can be cut down!\1"))
  if Kernel.pbConfirmMessage(_INTL("Would you like to cut it?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    pbHiddenMoveAnimation(movefinder)
    return true
  end
  return false
end

HiddenMoveHandlers::CanUseMove.add(:CUT,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORCUT,showmsg)
   facingEvent = $game_player.pbFacingEvent
   if !facingEvent || facingEvent.name!="Tree"
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:CUT,proc{|move,pokemon|
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   facingEvent = $game_player.pbFacingEvent
   if facingEvent
     pbSmashEvent(facingEvent)
   end
   return true
})

def pbSmashEvent(event)
  return if !event
  if event.name=="Tree";    pbSEPlay("Cut",80)
  elsif event.name=="Rock"; pbSEPlay("Rock Smash",80)
  end
  pbMoveRoute(event,[
     PBMoveRoute::Wait,2,
     PBMoveRoute::TurnLeft,
     PBMoveRoute::Wait,2,
     PBMoveRoute::TurnRight,
     PBMoveRoute::Wait,2,
     PBMoveRoute::TurnUp,
     PBMoveRoute::Wait,2
  ])
  pbWait(2*2*4)
  event.erase
  $PokemonMap.addErasedEvent(event.id) if $PokemonMap
end



#===============================================================================
# Dig
#===============================================================================
HiddenMoveHandlers::CanUseMove.add(:DIG,proc{|move,pkmn,showmsg|
   escape = ($PokemonGlobal.escapePoint rescue nil)
   if !escape || escape==[]
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   if $game_player.pbHasDependentEvents?
     Kernel.pbMessage(_INTL("It can't be used when you have someone with you.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::ConfirmUseMove.add(:DIG,proc{|move,pkmn|
   escape = ($PokemonGlobal.escapePoint rescue nil)
   return false if !escape || escape==[]
   mapname = pbGetMapNameFromId(escape[0])
   return Kernel.pbConfirmMessage(_INTL("Want to escape from here and return to {1}?",mapname))
})

HiddenMoveHandlers::UseMove.add(:DIG,proc{|move,pokemon|
   escape = ($PokemonGlobal.escapePoint rescue nil)
   if escape
     if !pbHiddenMoveAnimation(pokemon)
       Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
     end
     pbFadeOutIn(99999){
        $game_temp.player_new_map_id    = escape[0]
        $game_temp.player_new_x         = escape[1]
        $game_temp.player_new_y         = escape[2]
        $game_temp.player_new_direction = escape[3]
        Kernel.pbCancelVehicles
        $scene.transfer_player
        $game_map.autoplay
        $game_map.refresh
     }
     pbEraseEscapePoint
     return true
   end
   return false
})



#===============================================================================
# Dive
#===============================================================================
def Kernel.pbDive
  divemap = pbGetMetadata($game_map.map_id,MetadataDiveMap)
  return false if !divemap
  move = getID(PBMoves,:DIVE)
  movefinder = Kernel.pbCheckMove(move)
  if !pbCheckHiddenMoveBadge(BADGEFORDIVE,false) || (!$DEBUG && !movefinder)
    Kernel.pbMessage(_INTL("The sea is deep here. A Pokémon may be able to go underwater."))
    return false
  end
  if Kernel.pbConfirmMessage(_INTL("The sea is deep here. Would you like to use Dive?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    pbHiddenMoveAnimation(movefinder)
    pbFadeOutIn(99999){
       $game_temp.player_new_map_id    = divemap
       $game_temp.player_new_x         = $game_player.x
       $game_temp.player_new_y         = $game_player.y
       $game_temp.player_new_direction = $game_player.direction
       Kernel.pbCancelVehicles
       $PokemonGlobal.diving = true
       Kernel.pbUpdateVehicle
       $scene.transfer_player(false)
       $game_map.autoplay
       $game_map.refresh
    }
    return true
  end
  return false
end

def Kernel.pbSurfacing
  return if !$PokemonGlobal.diving
  divemap = nil
  meta = pbLoadMetadata
  for i in 0...meta.length
    if meta[i] && meta[i][MetadataDiveMap] && meta[i][MetadataDiveMap]==$game_map.map_id
      divemap = i; break
    end
  end
  return if !divemap
  move = getID(PBMoves,:DIVE)
  movefinder = Kernel.pbCheckMove(move)
  if !pbCheckHiddenMoveBadge(BADGEFORDIVE,false) || (!$DEBUG && !movefinder)
    Kernel.pbMessage(_INTL("Light is filtering down from above. A Pokémon may be able to surface here."))
    return false
  end
  if Kernel.pbConfirmMessage(_INTL("Light is filtering down from above. Would you like to use Dive?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    pbHiddenMoveAnimation(movefinder)
    pbFadeOutIn(99999){
       $game_temp.player_new_map_id    = divemap
       $game_temp.player_new_x         = $game_player.x
       $game_temp.player_new_y         = $game_player.y
       $game_temp.player_new_direction = $game_player.direction
       Kernel.pbCancelVehicles
       $PokemonGlobal.surfing = true
       Kernel.pbUpdateVehicle
       $scene.transfer_player(false)
       surfbgm = pbGetMetadata(0,MetadataSurfBGM)
       (surfbgm) ?  pbBGMPlay(surfbgm) : $game_map.autoplayAsCue
       $game_map.refresh
    }
    return true
  end
  return false
end

def Kernel.pbTransferUnderwater(mapid,xcoord,ycoord,direction=$game_player.direction)
  pbFadeOutIn(99999){
     $game_temp.player_new_map_id    = mapid
     $game_temp.player_new_x         = xcoord
     $game_temp.player_new_y         = ycoord
     $game_temp.player_new_direction = direction
     Kernel.pbCancelVehicles
     $PokemonGlobal.diving = true
     Kernel.pbUpdateVehicle
     $scene.transfer_player(false)
     $game_map.autoplay
     $game_map.refresh
  }
end

Events.onAction+=proc{|sender,e|
   if $PokemonGlobal.diving
     if DIVINGSURFACEANYWHERE
       Kernel.pbSurfacing
       return
     end
     divemap = nil
     meta = pbLoadMetadata
     for i in 0...meta.length
       if meta[i] && meta[i][MetadataDiveMap] && meta[i][MetadataDiveMap]==$game_map.map_id
         divemap = i; break
       end
     end
     if PBTerrain.isDeepWater?($MapFactory.getTerrainTag(divemap,$game_player.x,$game_player.y))
       Kernel.pbSurfacing
       return
     end
   else
     if PBTerrain.isDeepWater?($game_player.terrain_tag)
       Kernel.pbDive
       return
     end
   end
}

HiddenMoveHandlers::CanUseMove.add(:DIVE,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORDIVE,showmsg)
   if $PokemonGlobal.diving
     return true if DIVINGSURFACEANYWHERE
     divemap = nil
     meta = pbLoadMetadata
     for i in 0...meta.length
       if meta[i] && meta[i][MetadataDiveMap] && meta[i][MetadataDiveMap]==$game_map.map_id
         divemap = i; break
       end
     end
     if !PBTerrain.isDeepWater?($MapFactory.getTerrainTag(divemap,$game_player.x,$game_player.y))
       Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
       return false
     end
   else
     if !pbGetMetadata($game_map.map_id,MetadataDiveMap)
       Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
       return false
     end
     if !PBTerrain.isDeepWater?($game_player.terrain_tag)
       Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
       return false
     end
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:DIVE,proc{|move,pokemon|
   wasdiving = $PokemonGlobal.diving
   if $PokemonGlobal.diving
     divemap = nil
     meta = pbLoadMetadata
     for i in 0...meta.length
       if meta[i] && meta[i][MetadataDiveMap] && meta[i][MetadataDiveMap]==$game_map.map_id
         divemap = i; break
       end
     end
   else
     divemap = pbGetMetadata($game_map.map_id,MetadataDiveMap)
   end
   return false if !divemap
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   pbFadeOutIn(99999){
      $game_temp.player_new_map_id    = divemap
      $game_temp.player_new_x         = $game_player.x
      $game_temp.player_new_y         = $game_player.y
      $game_temp.player_new_direction = $game_player.direction
      Kernel.pbCancelVehicles
      (wasdiving) ? $PokemonGlobal.surfing = true : $PokemonGlobal.diving = true
      Kernel.pbUpdateVehicle
      $scene.transfer_player(false)
      $game_map.autoplay
      $game_map.refresh
   }
   return true
})



#===============================================================================
# Flash
#===============================================================================
HiddenMoveHandlers::CanUseMove.add(:FLASH,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORFLASH,showmsg)
   if !pbGetMetadata($game_map.map_id,MetadataDarkMap)
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   if $PokemonGlobal.flashUsed
     Kernel.pbMessage(_INTL("Flash is already being used.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:FLASH,proc{|move,pokemon|
   darkness = $PokemonTemp.darknessSprite
   return false if !darkness || darkness.disposed?
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   $PokemonGlobal.flashUsed = true
   while darkness.radius<176
     Graphics.update
     Input.update
     pbUpdateSceneMap
     darkness.radius += 4
   end
   return true
})



#===============================================================================
# Fly
#===============================================================================
HiddenMoveHandlers::CanUseMove.add(:FLY,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORFLY,showmsg)
   if $game_player.pbHasDependentEvents?
     Kernel.pbMessage(_INTL("It can't be used when you have someone with you.")) if showmsg
     return false
   end
   if !pbGetMetadata($game_map.map_id,MetadataOutdoor)
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:FLY,proc{|move,pokemon|
   if !$PokemonTemp.flydata
     Kernel.pbMessage(_INTL("Can't use that here."))
     return false
   end
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   pbFadeOutIn(99999){
      $game_temp.player_new_map_id    = $PokemonTemp.flydata[0]
      $game_temp.player_new_x         = $PokemonTemp.flydata[1]
      $game_temp.player_new_y         = $PokemonTemp.flydata[2]
      $game_temp.player_new_direction = 2
      Kernel.pbCancelVehicles
      $PokemonTemp.flydata = nil
      $scene.transfer_player
      $game_map.autoplay
      $game_map.refresh
   }
   pbEraseEscapePoint
   return true
})



#===============================================================================
# Headbutt
#===============================================================================
def Kernel.pbHeadbuttEffect(event)
  a = (event.x+(event.x/24).floor+1)*(event.y+(event.y/24).floor+1)
  a = (a*2/5)%10   # Even 2x as likely as odd, 0 is 1.5x as likely as odd
  b = ($Trainer.publicID)%10   # Practically equal odds of each value
  chance = 1                             # ~50%
  if a==b;                  chance = 8   # 10%
  elsif a>b && (a-b).abs<5; chance = 5   # ~30.3%
  elsif a<b && (a-b).abs>5; chance = 5   # ~9.7%
  end
  if rand(10)>=chance
    Kernel.pbMessage(_INTL("Nope. Nothing..."))
  else
    enctype = (chance==1) ? EncounterTypes::HeadbuttLow : EncounterTypes::HeadbuttHigh
    if !pbEncounter(enctype)
      Kernel.pbMessage(_INTL("Nope. Nothing..."))
    end
  end
end

def Kernel.pbHeadbutt(event)
  move = getID(PBMoves,:HEADBUTT)
  movefinder = Kernel.pbCheckMove(move)
  if !$DEBUG && !movefinder
    Kernel.pbMessage(_INTL("A Pokémon could be in this tree. Maybe a Pokémon could shake it."))
    return false
  end
  if Kernel.pbConfirmMessage(_INTL("A Pokémon could be in this tree. Would you like to use Headbutt?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    pbHiddenMoveAnimation(movefinder)
    Kernel.pbHeadbuttEffect(event)
    return true
  end
  return false
end

HiddenMoveHandlers::CanUseMove.add(:HEADBUTT,proc{|move,pkmn,showmsg|
   facingEvent = $game_player.pbFacingEvent
   if !facingEvent || facingEvent.name!="HeadbuttTree"
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:HEADBUTT,proc{|move,pokemon|
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   facingEvent = $game_player.pbFacingEvent
   Kernel.pbHeadbuttEffect(facingEvent)
})



#===============================================================================
# Rock Smash
#===============================================================================
def pbRockSmashRandomEncounter
  if rand(100)<25
    pbEncounter(EncounterTypes::RockSmash)
  end
end

def Kernel.pbRockSmash
  move = getID(PBMoves,:ROCKSMASH)
  movefinder = Kernel.pbCheckMove(move)
  if !pbCheckHiddenMoveBadge(BADGEFORROCKSMASH,false) || (!$DEBUG && !movefinder)
    Kernel.pbMessage(_INTL("It's a rugged rock, but a Pokémon may be able to smash it."))
    return false
  end
  if Kernel.pbConfirmMessage(_INTL("This rock appears to be breakable. Would you like to use Rock Smash?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    pbHiddenMoveAnimation(movefinder)
    return true
  end
  return false
end

HiddenMoveHandlers::CanUseMove.add(:ROCKSMASH,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORROCKSMASH,showmsg)
   facingEvent = $game_player.pbFacingEvent
   if !facingEvent || facingEvent.name!="Rock"
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:ROCKSMASH,proc{|move,pokemon|
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   facingEvent = $game_player.pbFacingEvent
   if facingEvent
     pbSmashEvent(facingEvent)
     pbRockSmashRandomEncounter
   end
   return true
})



#===============================================================================
# Strength
#===============================================================================
def Kernel.pbStrength
  if $PokemonMap.strengthUsed
    Kernel.pbMessage(_INTL("Strength made it possible to move boulders around."))
    return false
  end
  move = getID(PBMoves,:STRENGTH)
  movefinder = Kernel.pbCheckMove(move)
  if !pbCheckHiddenMoveBadge(BADGEFORSTRENGTH,false) || (!$DEBUG && !movefinder)
    Kernel.pbMessage(_INTL("It's a big boulder, but a Pokémon may be able to push it aside."))
    return false
  end
  Kernel.pbMessage(_INTL("It's a big boulder, but a Pokémon may be able to push it aside.\1"))
  if Kernel.pbConfirmMessage(_INTL("Would you like to use Strength?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    pbHiddenMoveAnimation(movefinder)
    Kernel.pbMessage(_INTL("{1}'s Strength made it possible to move boulders around!",speciesname))
    $PokemonMap.strengthUsed = true
    return true
  end
  return false
end

Events.onAction+=proc{|sender,e|
   facingEvent = $game_player.pbFacingEvent
   if facingEvent && facingEvent.name=="Boulder"
     Kernel.pbStrength
   end
}

HiddenMoveHandlers::CanUseMove.add(:STRENGTH,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORSTRENGTH,showmsg)
   if $PokemonMap.strengthUsed
     Kernel.pbMessage(_INTL("Strength is already being used.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:STRENGTH,proc{|move,pokemon|
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!\1",pokemon.name,PBMoves.getName(move)))
   end
   Kernel.pbMessage(_INTL("{1}'s Strength made it possible to move boulders around!",pokemon.name))
   $PokemonMap.strengthUsed = true
   return true
})



#===============================================================================
# Surf
#===============================================================================
def Kernel.pbSurf
  return false if $game_player.pbHasDependentEvents?
  move = getID(PBMoves,:SURF)
  movefinder = Kernel.pbCheckMove(move)
  if !pbCheckHiddenMoveBadge(BADGEFORSURF,false) || (!$DEBUG && !movefinder)
    return false
  end
  if Kernel.pbConfirmMessage(_INTL("The water is a deep blue...\nWould you like to surf on it?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    Kernel.pbCancelVehicles
    pbHiddenMoveAnimation(movefinder)
    surfbgm = pbGetMetadata(0,MetadataSurfBGM)
    pbCueBGM(surfbgm,0.5) if surfbgm
    pbStartSurfing
    return true
  end
  return false
end

def pbStartSurfing
  Kernel.pbCancelVehicles
  $PokemonEncounters.clearStepCount
  $PokemonGlobal.surfing = true
  $PokemonTemp.surfJump = $MapFactory.getFacingCoords($game_player.x,$game_player.y,$game_player.direction)
  Kernel.pbUpdateVehicle
  Kernel.pbJumpToward
  $PokemonTemp.surfJump = nil
  Kernel.pbUpdateVehicle
  $game_player.check_event_trigger_here([1,2])
end

def pbEndSurf(xOffset,yOffset)
  return false if !$PokemonGlobal.surfing
  x = $game_player.x
  y = $game_player.y
  currentTag = $game_map.terrain_tag(x,y)
  facingTag = Kernel.pbFacingTerrainTag
  if PBTerrain.isSurfable?(currentTag) && !PBTerrain.isSurfable?(facingTag)
    $PokemonTemp.surfJump = [x,y]
    if Kernel.pbJumpToward(1,false,true)
      $game_map.autoplayAsCue
      $game_player.increase_steps
      result = $game_player.check_event_trigger_here([1,2])
      Kernel.pbOnStepTaken(result)
    end
    $PokemonTemp.surfJump = nil
    return true
  end
  return false
end

def Kernel.pbTransferSurfing(mapid,xcoord,ycoord,direction=$game_player.direction)
  pbFadeOutIn(99999){
     $game_temp.player_new_map_id    = mapid
     $game_temp.player_new_x         = xcoord
     $game_temp.player_new_y         = ycoord
     $game_temp.player_new_direction = direction
     Kernel.pbCancelVehicles
     $PokemonGlobal.surfing = true
     Kernel.pbUpdateVehicle
     $scene.transfer_player(false)
     $game_map.autoplay
     $game_map.refresh
  }
end

Events.onAction+=proc{|sender,e|
   return if $PokemonGlobal.surfing
   return if pbGetMetadata($game_map.map_id,MetadataBicycleAlways)
   return if !PBTerrain.isSurfable?(Kernel.pbFacingTerrainTag)
   return if !$game_map.passable?($game_player.x,$game_player.y,$game_player.direction,$game_player)
   Kernel.pbSurf
}

HiddenMoveHandlers::CanUseMove.add(:SURF,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORSURF,showmsg)
   if $PokemonGlobal.surfing
     Kernel.pbMessage(_INTL("You're already surfing.")) if showmsg
     return false
   end
   if $game_player.pbHasDependentEvents?
     Kernel.pbMessage(_INTL("It can't be used when you have someone with you.")) if showmsg
     return false
   end
   if pbGetMetadata($game_map.map_id,MetadataBicycleAlways)
     Kernel.pbMessage(_INTL("Let's enjoy cycling!")) if showmsg
     return false
   end
   if !PBTerrain.isSurfable?(Kernel.pbFacingTerrainTag) ||
      !$game_map.passable?($game_player.x,$game_player.y,$game_player.direction,$game_player)
     Kernel.pbMessage(_INTL("No surfing here!")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:SURF,proc{|move,pokemon|
   $game_temp.in_menu = false
   Kernel.pbCancelVehicles
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   surfbgm = pbGetMetadata(0,MetadataSurfBGM)
   pbCueBGM(surfbgm,0.5) if surfbgm
   pbStartSurfing
   return true
})



#===============================================================================
# Sweet Scent
#===============================================================================
def pbSweetScent
  if $game_screen.weather_type!=PBFieldWeather::None
    Kernel.pbMessage(_INTL("The sweet scent faded for some reason..."))
    return
  end
  viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
  viewport.z = 99999
  count = 0
  viewport.color.alpha -= 10 
  begin
    if viewport.color.alpha<128 && count==0
      viewport.color.red   = 255
      viewport.color.green = 0
      viewport.color.blue  = 0
      viewport.color.alpha += 8
    else
      count += 1
      if count>10
        viewport.color.alpha -= 8 
      end
    end
    Graphics.update
    Input.update
    pbUpdateSceneMap
  end until viewport.color.alpha<=0
  viewport.dispose
  encounter = nil
  enctype = $PokemonEncounters.pbEncounterType
  if enctype<0 || !$PokemonEncounters.isEncounterPossibleHere? ||
     !pbEncounter(enctype)
    Kernel.pbMessage(_INTL("There appears to be nothing here..."))
  end
end

HiddenMoveHandlers::CanUseMove.add(:SWEETSCENT,proc{|move,pkmn,showmsg|
   return true
})

HiddenMoveHandlers::UseMove.add(:SWEETSCENT,proc{|move,pokemon|
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   pbSweetScent
   return true
})



#===============================================================================
# Teleport
#===============================================================================
HiddenMoveHandlers::CanUseMove.add(:TELEPORT,proc{|move,pkmn,showmsg|
   if !pbGetMetadata($game_map.map_id,MetadataOutdoor)
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   healing = $PokemonGlobal.healingSpot
   healing = pbGetMetadata(0,MetadataHome) if !healing   # Home
   if !healing
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   if $game_player.pbHasDependentEvents?
     Kernel.pbMessage(_INTL("It can't be used when you have someone with you.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::ConfirmUseMove.add(:TELEPORT,proc{|move,pkmn|
   healing = $PokemonGlobal.healingSpot
   healing = pbGetMetadata(0,MetadataHome) if !healing   # Home
   return false if !healing
   mapname = pbGetMapNameFromId(healing[0])
   return Kernel.pbConfirmMessage(_INTL("Want to return to the healing spot used last in {1}?",mapname))
})

HiddenMoveHandlers::UseMove.add(:TELEPORT,proc{|move,pokemon|
   healing = $PokemonGlobal.healingSpot
   healing = pbGetMetadata(0,MetadataHome) if !healing   # Home
   return false if !healing
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   pbFadeOutIn(99999){
      $game_temp.player_new_map_id    = healing[0]
      $game_temp.player_new_x         = healing[1]
      $game_temp.player_new_y         = healing[2]
      $game_temp.player_new_direction = 2
      Kernel.pbCancelVehicles
      $scene.transfer_player
      $game_map.autoplay
      $game_map.refresh
   }
   pbEraseEscapePoint
   return true
})



#===============================================================================
# Waterfall
#===============================================================================
def Kernel.pbAscendWaterfall(event=nil)
  event = $game_player if !event
  return if !event
  return if event.direction!=8   # can't ascend if not facing up
  oldthrough   = event.through
  oldmovespeed = event.move_speed
  terrain = Kernel.pbFacingTerrainTag
  return if !PBTerrain.isWaterfall?(terrain)
  event.through = true
  event.move_speed = 2
  loop do
    event.move_up
    terrain = pbGetTerrainTag(event)
    break if !PBTerrain.isWaterfall?(terrain)
  end
  event.through    = oldthrough
  event.move_speed = oldmovespeed
end

def Kernel.pbDescendWaterfall(event=nil)
  event = $game_player if !event
  return if !event
  return if event.direction!=2   # Can't descend if not facing down
  oldthrough   = event.through
  oldmovespeed = event.move_speed
  terrain = Kernel.pbFacingTerrainTag
  return if !PBTerrain.isWaterfall?(terrain)
  event.through = true
  event.move_speed = 2
  loop do
    event.move_down
    terrain = pbGetTerrainTag(event)
    break if !PBTerrain.isWaterfall?(terrain)
  end
  event.through    = oldthrough
  event.move_speed = oldmovespeed
end

def Kernel.pbWaterfall
  move = getID(PBMoves,:WATERFALL)
  movefinder = Kernel.pbCheckMove(move)
  if !pbCheckHiddenMoveBadge(BADGEFORWATERFALL,false) || (!$DEBUG && !movefinder)
    Kernel.pbMessage(_INTL("A wall of water is crashing down with a mighty roar."))
    return false
  end
  if Kernel.pbConfirmMessage(_INTL("It's a large waterfall. Would you like to use Waterfall?"))
    speciesname = (movefinder) ? movefinder.name : $Trainer.name
    Kernel.pbMessage(_INTL("{1} used {2}!",speciesname,PBMoves.getName(move)))
    pbHiddenMoveAnimation(movefinder)
    pbAscendWaterfall
    return true
  end
  return false
end

Events.onAction+=proc{|sender,e|
   terrain = Kernel.pbFacingTerrainTag
   if terrain==PBTerrain::Waterfall
     Kernel.pbWaterfall
     return
   elsif terrain==PBTerrain::WaterfallCrest
     Kernel.pbMessage(_INTL("A wall of water is crashing down with a mighty roar."))
     return
   end
}

HiddenMoveHandlers::CanUseMove.add(:WATERFALL,proc{|move,pkmn,showmsg|
   return false if !pbCheckHiddenMoveBadge(BADGEFORWATERFALL,showmsg)
   if Kernel.pbFacingTerrainTag!=PBTerrain::Waterfall
     Kernel.pbMessage(_INTL("Can't use that here.")) if showmsg
     return false
   end
   return true
})

HiddenMoveHandlers::UseMove.add(:WATERFALL,proc{|move,pokemon|
   if !pbHiddenMoveAnimation(pokemon)
     Kernel.pbMessage(_INTL("{1} used {2}!",pokemon.name,PBMoves.getName(move)))
   end
   Kernel.pbAscendWaterfall
   return true
})