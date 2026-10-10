#===============================================================================
# Load Pokémon sprites
#===============================================================================
def pbPokemonBitmapFile(species,shiny,back=false)   # Unused
  if shiny
    # Load shiny bitmap
    ret = sprintf("Graphics/Battlers/%ss%s",getConstantName(PBSpecies,species),back ? "b" : "") rescue nil
    if !pbResolveBitmap(ret)
      ret = sprintf("Graphics/Battlers/%03ds%s",species,(back) ? "b" : "")
    end
    return ret
  else
    # Load normal bitmap
    ret = sprintf("Graphics/Battlers/%s%s",getConstantName(PBSpecies,species),back ? "b" : "") rescue nil
    if !pbResolveBitmap(ret)
      ret = sprintf("Graphics/Battlers/%03d%s",species,(back) ? "b" : "")
    end
    return ret
  end
end

def pbLoadPokemonBitmap(pokemon,back=false)
  return pbLoadPokemonBitmapSpecies(pokemon,pokemon.species,back)
end

# Note: Returns an AnimatedBitmap, not a Bitmap
def pbLoadPokemonBitmapSpecies(pokemon,species,back=false)
  ret = nil
  if pokemon.egg?
    bitmapFileName = sprintf("Graphics/Battlers/%segg_%d",getConstantName(PBSpecies,species),pokemon.form) rescue nil
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = sprintf("Graphics/Battlers/%03degg_%d",species,pokemon.form)
      if !pbResolveBitmap(bitmapFileName)
        bitmapFileName = sprintf("Graphics/Battlers/%segg",getConstantName(PBSpecies,species)) rescue nil
        if !pbResolveBitmap(bitmapFileName)
          bitmapFileName = sprintf("Graphics/Battlers/%03degg",species)
          if !pbResolveBitmap(bitmapFileName)
            bitmapFileName = sprintf("Graphics/Battlers/egg")
          end
        end
      end
    end
    bitmapFileName = pbResolveBitmap(bitmapFileName)
  else
    bitmapFileName = pbCheckPokemonBitmapFiles([species,back,(pokemon.isFemale?),
       pokemon.isShiny?,(pokemon.form rescue 0),(pokemon.isShadow? rescue false)])
    # Alter bitmap if supported
    alterBitmap = (MultipleForms.getFunction(species,"alterBitmap") rescue nil)
  end
  if bitmapFileName && alterBitmap
    animatedBitmap = AnimatedBitmap.new(bitmapFileName)
    copiedBitmap = animatedBitmap.copy
    animatedBitmap.dispose
    copiedBitmap.each {|bitmap| alterBitmap.call(pokemon,bitmap) }
    ret = copiedBitmap
  elsif bitmapFileName
    ret = AnimatedBitmap.new(bitmapFileName)
  end
  return ret
end

# Note: Returns an AnimatedBitmap, not a Bitmap
def pbLoadSpeciesBitmap(species,female=false,form=0,shiny=false,shadow=false,back=false,egg=false)
  ret = nil
  if egg
    bitmapFileName = sprintf("Graphics/Battlers/%segg_%d",getConstantName(PBSpecies,species),form) rescue nil
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = sprintf("Graphics/Battlers/%03degg_%d",species,form)
      if !pbResolveBitmap(bitmapFileName)
        bitmapFileName = sprintf("Graphics/Battlers/%segg",getConstantName(PBSpecies,species)) rescue nil
        if !pbResolveBitmap(bitmapFileName)
          bitmapFileName = sprintf("Graphics/Battlers/%03degg",species)
          if !pbResolveBitmap(bitmapFileName)
            bitmapFileName = sprintf("Graphics/Battlers/egg")
          end
        end
      end
    end
    bitmapFileName = pbResolveBitmap(bitmapFileName)
  else
    bitmapFileName = pbCheckPokemonBitmapFiles([species,back,female,shiny,form,shadow])
  end
  if bitmapFileName
    ret = AnimatedBitmap.new(bitmapFileName)
  end
  return ret
end

def pbCheckPokemonBitmapFiles(params)
  species = params[0]
  back    = params[1]
  factors = []
  factors.push([5,params[5],false]) if params[5] && params[5]!=false     # shadow
  factors.push([2,params[2],false]) if params[2] && params[2]!=false     # gender
  factors.push([3,params[3],false]) if params[3] && params[3]!=false     # shiny
  factors.push([4,params[4].to_s,""]) if params[4] && params[4].to_s!="" &&
                                                      params[4].to_s!="0" # form
  tshadow = false
  tgender = false
  tshiny  = false
  tform   = ""
  for i in 0...2**factors.length
    for j in 0...factors.length
      case factors[j][0]
      when 2   # gender
        tgender = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
      when 3   # shiny
        tshiny = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
      when 4   # form
        tform = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
      when 5   # shadow
        tshadow = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
      end
    end
    bitmapFileName = sprintf("Graphics/Battlers/%s%s%s%s%s%s",
       getConstantName(PBSpecies,species),
       (tgender) ? "f" : "",
       (tshiny) ? "s" : "",
       (back) ? "b" : "",
       (tform!="") ? "_"+tform : "",
       (tshadow) ? "_shadow" : "") rescue nil
    ret = pbResolveBitmap(bitmapFileName)
    return ret if ret
    bitmapFileName = sprintf("Graphics/Battlers/%03d%s%s%s%s%s",
       species,
       (tgender) ? "f" : "",
       (tshiny) ? "s" : "",
       (back) ? "b" : "",
       (tform!="") ? "_"+tform : "",
       (tshadow) ? "_shadow" : "")
    ret = pbResolveBitmap(bitmapFileName)
    return ret if ret
  end
  return nil
end



#===============================================================================
# Load Pokémon icons
#===============================================================================
def pbLoadPokemonIcon(pokemon)
  return AnimatedBitmap.new(pbPokemonIconFile(pokemon)).deanimate
end

def pbPokemonIconFile(pokemon)
  bitmapFileName = nil
  bitmapFileName = pbCheckPokemonIconFiles([pokemon.species,(pokemon.isFemale?),
     pokemon.isShiny?,(pokemon.form rescue 0),(pokemon.isShadow? rescue false)],
     pokemon.egg?)
  return bitmapFileName
end

def pbCheckPokemonIconFiles(params,egg=false)
  species = params[0]
  if egg
    bitmapFileName = sprintf("Graphics/Icons/icon%segg_%d",getConstantName(PBSpecies,species),params[3]) rescue nil
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = sprintf("Graphics/Icons/icon%03degg_%d",species,params[3]) 
      if !pbResolveBitmap(bitmapFileName)
        bitmapFileName = sprintf("Graphics/Icons/icon%segg",getConstantName(PBSpecies,species)) rescue nil
        if !pbResolveBitmap(bitmapFileName)
          bitmapFileName = sprintf("Graphics/Icons/icon%03degg",species) 
          if !pbResolveBitmap(bitmapFileName)
            bitmapFileName = sprintf("Graphics/Icons/iconEgg")
          end
        end
      end
    end
    return pbResolveBitmap(bitmapFileName)
  else
    factors = []
    factors.push([4,params[4],false]) if params[4] && params[4]!=false     # shadow
    factors.push([1,params[1],false]) if params[1] && params[1]!=false     # gender
    factors.push([2,params[2],false]) if params[2] && params[2]!=false     # shiny
    factors.push([3,params[3].to_s,""]) if params[3] && params[3].to_s!="" &&
                                                        params[3].to_s!="0" # form
    tshadow = false
    tgender = false
    tshiny  = false
    tform   = ""
    for i in 0...2**factors.length
      for j in 0...factors.length
        case factors[j][0]
        when 1   # gender
          tgender = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
        when 2   # shiny
          tshiny = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
        when 3   # form
          tform = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
        when 4   # shadow
          tshadow = ((i/(2**j))%2==0) ? factors[j][1] : factors[j][2]
        end
      end
      bitmapFileName = sprintf("Graphics/Icons/icon%s%s%s%s%s",
         getConstantName(PBSpecies,species),
         (tgender) ? "f" : "",
         (tshiny) ? "s" : "",
         (tform!="") ? "_"+tform : "",
         (tshadow) ? "_shadow" : "") rescue nil
      ret = pbResolveBitmap(bitmapFileName)
      return ret if ret
      bitmapFileName = sprintf("Graphics/Icons/icon%03d%s%s%s%s",
         species,
         (tgender) ? "f" : "",
         (tshiny) ? "s" : "",
         (tform!="") ? "_"+tform : "",
         (tshadow) ? "_shadow" : "")
      ret = pbResolveBitmap(bitmapFileName)
      return ret if ret
    end
  end
  return nil
end



#===============================================================================
# Load Pokémon footprint graphics
#===============================================================================
def pbPokemonFootprintFile(pokemon,form=0)   # Used by the Pokédex
  return nil if !pokemon
  if pokemon.is_a?(Numeric)
    bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%s_%d",getConstantName(PBSpecies,pokemon),form) rescue nil
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%03d_%d",pokemon,form) rescue nil
      if !pbResolveBitmap(bitmapFileName)
        bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%s",getConstantName(PBSpecies,pokemon)) rescue nil
        if !pbResolveBitmap(bitmapFileName)
          bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%03d",pokemon)
        end
      end
    end
  else
    bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%s_%d",getConstantName(PBSpecies,pokemon.species),(pokemon.form rescue 0)) rescue nil
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%03d_%d",pokemon.species,(pokemon.form rescue 0)) rescue nil
      if !pbResolveBitmap(bitmapFileName)
        bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%s",getConstantName(PBSpecies,pokemon.species)) rescue nil
        if !pbResolveBitmap(bitmapFileName)
          bitmapFileName = sprintf("Graphics/Icons/Footprints/footprint%03d",pokemon.species)
        end
      end
    end
  end
  return pbResolveBitmap(bitmapFileName)
end



#===============================================================================
# Load item icons
#===============================================================================
def pbItemIconFile(item)
  return nil if !item
  bitmapFileName = nil
  if item==0
    bitmapFileName = sprintf("Graphics/Icons/itemBack")
  else
    bitmapFileName = sprintf("Graphics/Icons/item%s",getConstantName(PBItems,item)) rescue nil
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = sprintf("Graphics/Icons/item%03d",item)
      if !pbResolveBitmap(bitmapFileName) && pbIsMachine?(item)
        move = pbGetMachine(item)
        type = PBMoveData.new(move).type
        bitmapFileName = sprintf("Graphics/Icons/itemMachine%s",getConstantName(PBTypes,type)) rescue nil
        if !pbResolveBitmap(bitmapFileName)
          bitmapFileName = sprintf("Graphics/Icons/itemMachine%03d",type)
        end
      end
    end
  end
  return bitmapFileName
end

def pbHeldItemIconFile(item)   # Used in the party screen
  return nil if !item || item==0
  namebase = (pbIsMail?(item)) ? "mail" : "item"
  bitmapFileName = sprintf("Graphics/Pictures/Party/icon_%s_%s",namebase,getConstantName(PBItems,item)) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Pictures/Party/icon_%s_%03d",namebase,item)
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = sprintf("Graphics/Pictures/Party/icon_%s",namebase)
    end
  end
  return bitmapFileName
end



#===============================================================================
# Load mail background graphics
#===============================================================================
def pbMailBackFile(item)
  return nil if !item
  bitmapFileName = sprintf("Graphics/Pictures/Mail/mail_%s",getConstantName(PBItems,item)) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Pictures/Mail/mail_%03d",item)
  end
  return bitmapFileName
end



#===============================================================================
# Load NPC charsets
#===============================================================================
def pbTrainerCharFile(type)   # Used by the phone
  return nil if !type
  bitmapFileName = sprintf("Graphics/Characters/trchar%s",getConstantName(PBTrainers,type)) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Characters/trchar%03d",type)
  end
  return bitmapFileName
end

def pbTrainerCharNameFile(type)   # Used by Battle Frontier and compiler
  return nil if !type
  bitmapFileName = sprintf("trchar%s",getConstantName(PBTrainers,type)) rescue nil
  if !pbResolveBitmap(sprintf("Graphics/Characters/"+bitmapFileName))
    bitmapFileName = sprintf("trchar%03d",type)
  end
  return bitmapFileName
end



#===============================================================================
# Load trainer sprites
#===============================================================================
def pbTrainerSpriteFile(type)
  return nil if !type
  bitmapFileName = sprintf("Graphics/Characters/trainer%s",getConstantName(PBTrainers,type)) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Characters/trainer%03d",type)
  end
  return bitmapFileName
end

def pbTrainerSpriteBackFile(type)
  return nil if !type
  bitmapFileName = sprintf("Graphics/Characters/trback%s",getConstantName(PBTrainers,type)) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Characters/trback%03d",type)
  end
  return bitmapFileName
end

def pbPlayerSpriteFile(type)
  return nil if !type
  outfit = ($Trainer) ? $Trainer.outfit : 0
  bitmapFileName = sprintf("Graphics/Characters/trainer%s_%d",
     getConstantName(PBTrainers,type),outfit) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Characters/trainer%03d_%d",type,outfit)
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = pbTrainerSpriteFile(type)
    end
  end
  return bitmapFileName
end

def pbPlayerSpriteBackFile(type)
  return nil if !type
  outfit = ($Trainer) ? $Trainer.outfit : 0
  bitmapFileName = sprintf("Graphics/Characters/trback%s_%d",
     getConstantName(PBTrainers,type),outfit) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Characters/trback%03d_%d",type,outfit)
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = pbTrainerSpriteBackFile(type)
    end
  end
  return bitmapFileName
end



#===============================================================================
# Load player's head icons (used in the Town Map)
#===============================================================================
def pbTrainerHeadFile(type)
  return nil if !type
  bitmapFileName = sprintf("Graphics/Pictures/mapPlayer%s",getConstantName(PBTrainers,type)) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Pictures/mapPlayer%03d",type)
  end
  return bitmapFileName
end

def pbPlayerHeadFile(type)
  return nil if !type
  outfit = ($Trainer) ? $Trainer.outfit : 0
  bitmapFileName = sprintf("Graphics/Pictures/mapPlayer%s_%d",
     getConstantName(PBTrainers,type),outfit) rescue nil
  if !pbResolveBitmap(bitmapFileName)
    bitmapFileName = sprintf("Graphics/Pictures/mapPlayer%03d_%d",type,outfit)
    if !pbResolveBitmap(bitmapFileName)
      bitmapFileName = pbTrainerHeadFile(type)
    end
  end
  return bitmapFileName
end



#===============================================================================
# Analyse audio files
#===============================================================================
def pbResolveAudioSE(file)
  return nil if !file
  if RTP.exists?("Audio/SE/"+file,["",".wav",".mp3",".ogg"])
    return RTP.getPath("Audio/SE/"+file,["",".wav",".mp3",".ogg"])
  end
  return nil
end

def pbCryFrameLength(pokemon,form=0,pitch=nil)
  return 0 if !pokemon
  pitch = 100 if !pitch
  pitch = pitch.to_f/100
  return 0 if pitch<=0
  playtime = 0.0
  if pokemon.is_a?(Numeric)
    pkmnwav = pbResolveAudioSE(pbCryFile(pokemon,form))
    playtime = getPlayTime(pkmnwav) if pkmnwav
  elsif !pokemon.egg?
    if pokemon.respond_to?("chatter") && pokemon.chatter
      playtime = pokemon.chatter.time
      pitch = 1.0
    else
      pkmnwav = pbResolveAudioSE(pbCryFile(pokemon))
      playtime = getPlayTime(pkmnwav) if pkmnwav
    end 
  end
  playtime /= pitch # sound is lengthened the lower the pitch
  # 4 is added to provide a buffer between sounds
  return (playtime*Graphics.frame_rate).ceil+4
end



#===============================================================================
# Load/play Pokémon cry files
#===============================================================================
def pbPlayCry(pokemon,volume=90,pitch=nil)
  return if !pokemon
  if pokemon.is_a?(Numeric)
    pbPlayCrySpecies(pokemon,0,volume,pitch)
  elsif !pokemon.egg?
    if pokemon.respond_to?("chatter") && pokemon.chatter
      pokemon.chatter.play
    else
      pkmnwav = pbCryFile(pokemon)
      if pkmnwav
        pbSEPlay(RPG::AudioFile.new(pkmnwav,volume,
           (pitch) ? pitch : (pokemon.hp*25/pokemon.totalhp)+75)) rescue nil
      end
    end
  end
end

def pbPlayCrySpecies(pokemon,form=0,volume=90,pitch=nil)
  return if !pokemon
  if pokemon.is_a?(String) || pokemon.is_a?(Symbol)
    pokemon = getID(PBSpecies,pokemon)
  end
  if pokemon.is_a?(Numeric)
    pkmnwav = pbCryFile(pokemon,form)
    if pkmnwav
      pbSEPlay(RPG::AudioFile.new(pkmnwav,volume,(pitch) ? pitch : 100)) rescue nil
    end
  end
end

def pbCryFile(pokemon,form=0)
  return nil if !pokemon
  if pokemon.is_a?(String) || pokemon.is_a?(Symbol)
    pokemon = getID(PBSpecies,pokemon)
  end
  if pokemon.is_a?(Numeric)
    filename = sprintf("Cries/%sCry_%d",getConstantName(PBSpecies,pokemon),form) rescue nil
    if !pbResolveAudioSE(filename)
      filename = sprintf("Cries/%03dCry_%d",pokemon,form)
      if !pbResolveAudioSE(filename)
        filename = sprintf("Cries/%sCry",getConstantName(PBSpecies,pokemon)) rescue nil
        if !pbResolveAudioSE(filename)
          filename = sprintf("Cries/%03dCry",pokemon)
        end
      end
    end
    return filename if pbResolveAudioSE(filename)
  elsif !pokemon.egg?
    form = (pokemon.form rescue 0)
    filename = sprintf("Cries/%sCry_%d",getConstantName(PBSpecies,pokemon.species),form) rescue nil
    if !pbResolveAudioSE(filename)
      filename = sprintf("Cries/%03dCry_%d",pokemon.species,form)
      if !pbResolveAudioSE(filename)
        filename = sprintf("Cries/%sCry",getConstantName(PBSpecies,pokemon.species)) rescue nil
        if !pbResolveAudioSE(filename)
          filename = sprintf("Cries/%03dCry",pokemon.species)
        end
      end
    end
    return filename if pbResolveAudioSE(filename)
  end
  return nil
end



#===============================================================================
# Load various wild battle music
#===============================================================================
def pbGetWildBattleBGM(species)
  if $PokemonGlobal.nextBattleBGM
    return $PokemonGlobal.nextBattleBGM.clone
  end
  ret = nil
  if !ret && $game_map
    # Check map-specific metadata
    music = pbGetMetadata($game_map.map_id,MetadataMapWildBattleBGM)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  if !ret
    # Check global metadata
    music = pbGetMetadata(0,MetadataWildBattleBGM)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  ret = pbStringToAudioFile("Battle wild") if !ret
  return ret
end

def pbGetWildVictoryME
  if $PokemonGlobal.nextBattleME
    return $PokemonGlobal.nextBattleME.clone
  end
  ret = nil
  if !ret && $game_map
    # Check map-specific metadata
    music = pbGetMetadata($game_map.map_id,MetadataMapWildVictoryME)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  if !ret
    # Check global metadata
    music = pbGetMetadata(0,MetadataWildVictoryME)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  ret = pbStringToAudioFile("Battle victory") if !ret
  ret.name = "../../Audio/ME/"+ret.name
  return ret
end



#===============================================================================
# Load/play various trainer battle music
#===============================================================================
def pbPlayTrainerIntroME(trainertype)
  pbRgssOpen("Data/trainertypes.dat","rb"){|f|
     trainertypes = Marshal.load(f)
     if trainertypes[trainertype]
       bgm = trainertypes[trainertype][6]
       if bgm && bgm!=""
         bgm = pbStringToAudioFile(bgm)
         pbMEPlay(bgm)
         return
       end
     end
  }
end

def pbGetTrainerBattleBGM(trainer) # can be a PokeBattle_Trainer or an array of PokeBattle_Trainer
  if $PokemonGlobal.nextBattleBGM
    return $PokemonGlobal.nextBattleBGM.clone
  end
  ret = nil
  music = nil
  pbRgssOpen("Data/trainertypes.dat","rb"){|f|
     trainertypes = Marshal.load(f)
     trainerarray = (trainer.is_a?(Array)) ? trainer : [trainer]
     for i in 0...trainerarray.length
       trainertype = trainerarray[i].trainertype
       if trainertypes[trainertype]
         music = trainertypes[trainertype][4]
       end
     end
  }
  if music && music!=""
    ret = pbStringToAudioFile(music)
  end
  if !ret && $game_map
    # Check map-specific metadata
    music = pbGetMetadata($game_map.map_id,MetadataMapTrainerBattleBGM)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  if !ret
    # Check global metadata
    music = pbGetMetadata(0,MetadataTrainerBattleBGM)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  ret = pbStringToAudioFile("Battle trainer") if !ret
  return ret
end

def pbGetTrainerBattleBGMFromType(trainertype)
  if $PokemonGlobal.nextBattleBGM
    return $PokemonGlobal.nextBattleBGM.clone
  end
  music = nil
  pbRgssOpen("Data/trainertypes.dat","rb"){|f|
    trainertypes = Marshal.load(f)
    if trainertypes[trainertype]
      music = trainertypes[trainertype][4]
    end
  }
  ret = nil
  if music && music!=""
    ret = pbStringToAudioFile(music)
  end
  if !ret && $game_map
    # Check map-specific metadata
    music = pbGetMetadata($game_map.map_id,MetadataMapTrainerBattleBGM)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  if !ret
    # Check global metadata
    music = pbGetMetadata(0,MetadataTrainerBattleBGM)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  ret = pbStringToAudioFile("Battle trainer") if !ret
  return ret
end

def pbGetTrainerVictoryME(trainer) # can be a PokeBattle_Trainer or an array of PokeBattle_Trainer
  if $PokemonGlobal.nextBattleME
    return $PokemonGlobal.nextBattleME.clone
  end
  music = nil
  pbRgssOpen("Data/trainertypes.dat","rb"){|f|
     trainertypes = Marshal.load(f)
     trainerarray = (trainer.is_a?(Array)) ? trainer : [trainer]
     for i in 0...trainerarray.length
       trainertype = trainerarray[i].trainertype
       if trainertypes[trainertype]
         music = trainertypes[trainertype][5]
       end
     end
  }
  ret = nil
  if music && music!=""
    ret = pbStringToAudioFile(music)
  end
  if !ret && $game_map
    # Check map-specific metadata
    music = pbGetMetadata($game_map.map_id,MetadataMapTrainerVictoryME)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  if !ret
    # Check global metadata
    music = pbGetMetadata(0,MetadataTrainerVictoryME)
    if music && music!=""
      ret = pbStringToAudioFile(music)
    end
  end
  ret = pbStringToAudioFile("Battle victory") if !ret
  ret.name = "../../Audio/ME/"+ret.name
  return ret
end