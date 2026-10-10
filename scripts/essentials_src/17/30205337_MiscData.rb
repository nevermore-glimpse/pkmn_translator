#===============================================================================
# Phone data
#===============================================================================
class PhoneDatabase
  attr_accessor :generics
  attr_accessor :greetings
  attr_accessor :greetingsMorning
  attr_accessor :greetingsEvening
  attr_accessor :bodies1
  attr_accessor :bodies2
  attr_accessor :battleRequests
  attr_accessor :trainers

  def initialize
    @generics         = []
    @greetings        = []
    @greetingsMorning = []
    @greetingsEvening = []
    @bodies1          = []
    @bodies2          = []
    @battleRequests   = []
    @trainers         = []
  end
end



module PhoneMsgType
  Generic       = 0
  Greeting      = 1
  Body          = 2
  BattleRequest = 3 
end



#===============================================================================
# Global and map metadata
#===============================================================================
MetadataHome             = 1
MetadataWildBattleBGM    = 2
MetadataTrainerBattleBGM = 3
MetadataWildVictoryME    = 4
MetadataTrainerVictoryME = 5
MetadataSurfBGM          = 6
MetadataBicycleBGM       = 7
MetadataPlayerA          = 8
MetadataPlayerB          = 9
MetadataPlayerC          = 10
MetadataPlayerD          = 11
MetadataPlayerE          = 12
MetadataPlayerF          = 13
MetadataPlayerG          = 14
MetadataPlayerH          = 15

MetadataOutdoor             = 1
MetadataShowArea            = 2
MetadataBicycle             = 3
MetadataBicycleAlways       = 4
MetadataHealingSpot         = 5
MetadataWeather             = 6
MetadataMapPosition         = 7
MetadataDiveMap             = 8
MetadataDarkMap             = 9
MetadataSafariMap           = 10
MetadataSnapEdges           = 11
MetadataDungeon             = 12
MetadataBattleBack          = 13
MetadataMapWildBattleBGM    = 14
MetadataMapTrainerBattleBGM = 15
MetadataMapWildVictoryME    = 16
MetadataMapTrainerVictoryME = 17
MetadataMapSize             = 18



module PokemonMetadata
  GlobalTypes = {
     "Home"             => [MetadataHome,"uuuu"],
     "WildBattleBGM"    => [MetadataWildBattleBGM,"s"],
     "TrainerBattleBGM" => [MetadataTrainerBattleBGM,"s"],
     "WildVictoryME"    => [MetadataWildVictoryME,"s"],
     "TrainerVictoryME" => [MetadataTrainerVictoryME,"s"],
     "SurfBGM"          => [MetadataSurfBGM,"s"],
     "BicycleBGM"       => [MetadataBicycleBGM,"s"],
     "PlayerA"          => [MetadataPlayerA,"esssssss",:PBTrainers],
     "PlayerB"          => [MetadataPlayerB,"esssssss",:PBTrainers],
     "PlayerC"          => [MetadataPlayerC,"esssssss",:PBTrainers],
     "PlayerD"          => [MetadataPlayerD,"esssssss",:PBTrainers],
     "PlayerE"          => [MetadataPlayerE,"esssssss",:PBTrainers],
     "PlayerF"          => [MetadataPlayerF,"esssssss",:PBTrainers],
     "PlayerG"          => [MetadataPlayerG,"esssssss",:PBTrainers],
     "PlayerH"          => [MetadataPlayerH,"esssssss",:PBTrainers]
  }
  NonGlobalTypes = {
     "Outdoor"          => [MetadataOutdoor,"b"],
     "ShowArea"         => [MetadataShowArea,"b"],
     "Bicycle"          => [MetadataBicycle,"b"],
     "BicycleAlways"    => [MetadataBicycleAlways,"b"],
     "HealingSpot"      => [MetadataHealingSpot,"uuu"],
     "Weather"          => [MetadataWeather,"eu",:PBFieldWeather],
     "MapPosition"      => [MetadataMapPosition,"uuu"],
     "DiveMap"          => [MetadataDiveMap,"u"],
     "DarkMap"          => [MetadataDarkMap,"b"],
     "SafariMap"        => [MetadataSafariMap,"b"],
     "SnapEdges"        => [MetadataSnapEdges,"b"],
     "Dungeon"          => [MetadataDungeon,"b"],
     "BattleBack"       => [MetadataBattleBack,"s"],
     "WildBattleBGM"    => [MetadataMapWildBattleBGM,"s"],
     "TrainerBattleBGM" => [MetadataMapTrainerBattleBGM,"s"],
     "WildVictoryME"    => [MetadataMapWildVictoryME,"s"],
     "TrainerVictoryME" => [MetadataMapTrainerVictoryME,"s"],
     "MapSize"          => [MetadataMapSize,"us"],
  }
end



#===============================================================================
# Manipulation methods for metadata, phone data and Pokémon species data
#===============================================================================
def pbLoadMetadata
  $PokemonTemp = PokemonTemp.new if !$PokemonTemp
  if !$PokemonTemp.pokemonMetadata
    if !pbRgssExists?("Data/metadata.dat")
      $PokemonTemp.pokemonMetadata = []
    else
      $PokemonTemp.pokemonMetadata = load_data("Data/metadata.dat")
    end
  end
  return $PokemonTemp.pokemonMetadata
end

def pbGetMetadata(mapid,metadataType)
  meta = pbLoadMetadata
  return meta[mapid][metadataType] if meta[mapid]
  return nil
end

def pbLoadPhoneData
  $PokemonTemp = PokemonTemp.new if !$PokemonTemp
  if !$PokemonTemp.pokemonPhoneData
    pbRgssOpen("Data/phone.dat","rb"){|f|
      $PokemonTemp.pokemonPhoneData = Marshal.load(f)
    }
  end
  return $PokemonTemp.pokemonPhoneData
end

def pbOpenDexData
  $PokemonTemp = PokemonTemp.new if !$PokemonTemp
  if !$PokemonTemp.pokemonDexData
    pbRgssOpen("Data/dexdata.dat","rb"){|f|
      $PokemonTemp.pokemonDexData = f.read
    }
  end
  if block_given?
    StringInput.open($PokemonTemp.pokemonDexData) {|f| yield f }
  else
    return StringInput.open($PokemonTemp.pokemonDexData)
  end
end

def pbDexDataOffset(dexdata,species,offset)
  dexdata.pos = 76*(species-1)+offset
end

def pbLoadFormsData
  $PokemonTemp = PokemonTemp.new if !$PokemonTemp
  if !$PokemonTemp.pokemonFormsData
    File.open("Data/formspecies.dat"){|f|
      $PokemonTemp.pokemonFormsData = Marshal.load(f)
    }
  end
  return $PokemonTemp.pokemonFormsData
end

def pbClearData
  if $PokemonTemp
    $PokemonTemp.pokemonDexData   = nil
    $PokemonTemp.pokemonFormsData = nil
    $PokemonTemp.pokemonMetadata  = nil
    $PokemonTemp.pokemonPhoneData = nil
  end
  MapFactoryHelper.clear
  if $game_map && $PokemonEncounters
    $PokemonEncounters.setup($game_map.map_id)
  end
  if pbRgssExists?("Data/Tilesets.rxdata")
    $data_tilesets = load_data("Data/Tilesets.rxdata")
  end
  if pbRgssExists?("Data/Tilesets.rvdata")
    $data_tilesets = load_data("Data/Tilesets.rvdata")
  end
end