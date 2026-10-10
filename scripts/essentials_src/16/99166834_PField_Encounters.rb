module EncounterTypes
  Land         = 0
  Cave         = 1
  Water        = 2
  RockSmash    = 3
  OldRod       = 4
  GoodRod      = 5
  SuperRod     = 6
  HeadbuttLow  = 7
  HeadbuttHigh = 8
  LandMorning  = 9
  LandDay      = 10
  LandNight    = 11
  BugContest   = 12
  Names=[
     "Land",
     "Cave",
     "Water",
     "RockSmash",
     "OldRod",
     "GoodRod",
     "SuperRod",
     "HeadbuttLow",
     "HeadbuttHigh",
     "LandMorning",
     "LandDay",
     "LandNight",
     "BugContest"
  ]
  EnctypeChances=[
     [20,20,10,10,10,10,5,5,4,4,1,1],
     [20,20,10,10,10,10,5,5,4,4,1,1],
     [60,30,5,4,1],
     [60,30,5,4,1],
     [70,30],
     [60,20,20],
     [40,40,15,4,1],
     [30,25,20,10,5,5,4,1],
     [30,25,20,10,5,5,4,1],
     [20,20,10,10,10,10,5,5,4,4,1,1],
     [20,20,10,10,10,10,5,5,4,4,1,1],
     [20,20,10,10,10,10,5,5,4,4,1,1],
     [20,20,10,10,10,10,5,5,4,4,1,1]
  ]
  EnctypeDensities=[25,10,10,0,0,0,0,0,0,25,25,25,25]
  EnctypeCompileDens=[1,2,3,0,0,0,0,0,0,1,1,1,1]
end



class PokemonEncounters
  def initialize
    @enctypes=[]
    @density=nil
  end

  def stepcount
    return @stepcount
  end

  def clearStepCount
    @stepcount=0
  end

  def hasEncounter?(enc)
    return false if @density==nil || enc<0
    return @enctypes[enc] ? true : false  
  end

  def isCave?
    return false if @density==nil
    return @enctypes[EncounterTypes::Cave] ? true : false
  end

  def isGrass?
    return false if @density==nil
    return (@enctypes[EncounterTypes::Land] ||
            @enctypes[EncounterTypes::LandMorning] ||
            @enctypes[EncounterTypes::LandDay] ||
            @enctypes[EncounterTypes::LandNight] ||
            @enctypes[EncounterTypes::BugContest]) ? true : false
  end

  def isRegularGrass?
    return false if @density==nil
    return (@enctypes[EncounterTypes::Land] ||
            @enctypes[EncounterTypes::LandMorning] ||
            @enctypes[EncounterTypes::LandDay] ||
            @enctypes[EncounterTypes::LandNight]) ? true : false
  end

  def isWater?
    return false if @density==nil
    return @enctypes[EncounterTypes::Water] ? true : false
  end

  def pbEncounterType
    if $PokemonGlobal && $PokemonGlobal.surfing
      return EncounterTypes::Water
    elsif self.isCave?
      return EncounterTypes::Cave
    elsif self.isGrass?
      time=pbGetTimeNow
      enctype=EncounterTypes::Land
      enctype=EncounterTypes::LandNight if self.hasEncounter?(EncounterTypes::LandNight) && PBDayNight.isNight?(time)
      enctype=EncounterTypes::LandDay if self.hasEncounter?(EncounterTypes::LandDay) && PBDayNight.isDay?(time)
      enctype=EncounterTypes::LandMorning if self.hasEncounter?(EncounterTypes::LandMorning) && PBDayNight.isMorning?(time)
      if pbInBugContest? && self.hasEncounter?(EncounterTypes::BugContest)
        enctype=EncounterTypes::BugContest
      end
      return enctype
    end
    return -1
  end

  def isEncounterPossibleHere?
    if $PokemonGlobal && $PokemonGlobal.surfing
      return true
    elsif PBTerrain.isIce?(pbGetTerrainTag($game_player))
      return false
    elsif self.isCave?
      return true
    elsif self.isGrass?
      return PBTerrain.isGrass?($game_map.terrain_tag($game_player.x,$game_player.y))
    end
    return false
  end

  def setup(mapID)
    @density=nil
    @stepcount=0
    @enctypes=[]
    begin
      data=load_data("Data/encounters.dat")
      if data.is_a?(Hash) && data[mapID]
        @density=data[mapID][0]
        @enctypes=data[mapID][1]
      else
        @density=nil
        @enctypes=[]
      end
    rescue
      @density=nil
      @enctypes=[]
    end
  end

  def pbMapHasEncounter?(mapID,enctype)
    data=load_data("Data/encounters.dat")
    if data.is_a?(Hash) && data[mapID]
      enctypes=data[mapID][1]
      density=data[mapID][0]
    else
      return false
    end
    return false if density==nil || enctype<0
    return enctypes[enctype] ? true : false  
  end

  def pbMapEncounter(mapID,enctype)
    if enctype<0 || enctype>EncounterTypes::EnctypeChances.length
      raise ArgumentError.new(_INTL("Encounter type out of range"))
    end
    data=load_data("Data/encounters.dat")
    if data.is_a?(Hash) && data[mapID]
      enctypes=data[mapID][1]
    else
      return nil
    end
    return nil if enctypes[enctype]==nil
    chances=EncounterTypes::EnctypeChances[enctype]
    chancetotal=0
    chances.each {|a| chancetotal+=a}
    rnd=rand(chancetotal)
    chosenpkmn=0
    chance=0
    for i in 0...chances.length
      chance+=chances[i]
      if rnd<chance
        chosenpkmn=i
        break
      end
    end
    encounter=enctypes[enctype][chosenpkmn]
    level=encounter[1]+rand(1+encounter[2]-encounter[1])
    return [encounter[0],level]
  end

  def pbEncounteredPokemon(enctype,tries=1)
    if enctype<0 || enctype>EncounterTypes::EnctypeChances.length
      raise ArgumentError.new(_INTL("Encounter type out of range"))
    end
    return nil if @enctypes[enctype]==nil
    encounters=@enctypes[enctype]
    chances=EncounterTypes::EnctypeChances[enctype]
    firstpoke=$Trainer.firstParty
    if firstpoke && !firstpoke.isEgg? && rand(2)==0
      if isConst?(firstpoke.ability,PBAbilities,:STATIC)
        newencs=[]; newchances=[]
        dexdata=pbOpenDexData
        for i in 0...encounters.length
          pbDexDataOffset(dexdata,encounters[i][0],8)
          t1=dexdata.fgetb
          t2=dexdata.fgetb
          if isConst?(t1,PBTypes,:ELECTRIC) || isConst?(t2,PBTypes,:ELECTRIC)
            newencs.push(encounters[i])
            newchances.push(chances[i])
          end
        end
        dexdata.close
        if newencs.length>0
          encounters=newencs
          chances=newchances
        end
      end
      if isConst?(firstpoke.ability,PBAbilities,:MAGNETPULL)
        newencs=[]; newchances=[]
        dexdata=pbOpenDexData
        for i in 0...encounters.length
          pbDexDataOffset(dexdata,encounters[i][0],8)
          t1=dexdata.fgetb
          t2=dexdata.fgetb
          if isConst?(t1,PBTypes,:STEEL) || isConst?(t2,PBTypes,:STEEL)
            newencs.push(encounters[i])
            newchances.push(chances[i])
          end
        end
        dexdata.close
        if newencs.length>0
          encounters=newencs
          chances=newchances
        end
      end
    end
    chancetotal=0
    chances.each {|a| chancetotal+=a}
    rnd=0
    tries.times do
      r=rand(chancetotal)
      rnd=r if rnd<r
    end
    chosenpkmn=0
    chance=0
    for i in 0...chances.length
      chance+=chances[i]
      if rnd<chance
        chosenpkmn=i
        break
      end
    end
    encounter=encounters[chosenpkmn]
    return nil if !encounter
    level=encounter[1]+rand(1+encounter[2]-encounter[1])
    if $Trainer.firstParty && !$Trainer.firstParty.isEgg? &&
       (isConst?($Trainer.firstParty.ability,PBAbilities,:HUSTLE) ||
       isConst?($Trainer.firstParty.ability,PBAbilities,:VITALSPIRIT) ||
       isConst?($Trainer.firstParty.ability,PBAbilities,:PRESSURE)) &&
       rand(2)==0
      level2=encounter[1]+rand(1+encounter[2]-encounter[1])
      level=[level,level2].max
    end
    if $PokemonMap.blackFluteUsed && USENEWBATTLEMECHANICS
      level=[level+1+rand(3),PBExperience::MAXLEVEL].min
    elsif $PokemonMap.whiteFluteUsed && USENEWBATTLEMECHANICS
      level=[level-1-rand(3),1].max
    end
    return [encounter[0],level]
  end

  def pbCanEncounter?(encounter)
    return false if $game_system.encounter_disabled
    return false if !encounter || !$Trainer
    return false if $DEBUG && Input.press?(Input::CTRL)
    if !pbPokeRadarOnShakingGrass
      return false if $PokemonGlobal.repel>0 && $Trainer.ablePokemonCount>0 &&
                      encounter[1]<=$Trainer.ablePokemonParty[0].level
    end
    return true
  end

  def pbGenerateEncounter(enctype)
    if enctype<0 || enctype>EncounterTypes::EnctypeChances.length
      raise ArgumentError.new(_INTL("Encounter type out of range"))
    end
    return nil if @density==nil
    return nil if @density[enctype]==0 || !@density[enctype]
    return nil if @enctypes[enctype]==nil
    @stepcount+=1
    return nil if @stepcount<=3 # Check three steps after battle ends
    encount=@density[enctype]*16
    if $PokemonGlobal.bicycle
      encount=(encount*0.8)
    end
    if $PokemonMap.blackFluteUsed && !USENEWBATTLEMECHANICS
      encount=(encount/2)
    elsif $PokemonMap.whiteFluteUsed && !USENEWBATTLEMECHANICS
      encount=(encount*1.5)
    end
    firstpoke=$Trainer.firstParty
    if firstpoke && !firstpoke.isEgg?
      if isConst?(firstpoke.item,PBItems,:CLEANSETAG)
        encount=(encount*2/3)
      elsif isConst?(firstpoke.item,PBItems,:PUREINCENSE)
        encount=(encount*2/3)
      else   # Ignore ability effects if an item effect applies
        if isConst?(firstpoke.ability,PBAbilities,:STENCH)
          encount=(encount/2)
        elsif isConst?(firstpoke.ability,PBAbilities,:WHITESMOKE)
          encount=(encount/2)
        elsif isConst?(firstpoke.ability,PBAbilities,:QUICKFEET)
          encount=(encount/2)
        elsif isConst?(firstpoke.ability,PBAbilities,:SNOWCLOAK) &&
           ($game_screen.weather_type==PBFieldWeather::Snow ||
           $game_screen.weather_type==PBFieldWeather::Blizzard)
          encount=(encount/2)
        elsif isConst?(firstpoke.ability,PBAbilities,:SANDVEIL) &&
           $game_screen.weather_type==PBFieldWeather::Sandstorm
          encount=(encount/2)
        elsif isConst?(firstpoke.ability,PBAbilities,:SWARM)
          encount=(encount*1.5)
        elsif isConst?(firstpoke.ability,PBAbilities,:ILLUMINATE)
          encount=(encount*2)
        elsif isConst?(firstpoke.ability,PBAbilities,:ARENATRAP)
          encount=(encount*2)
        elsif isConst?(firstpoke.ability,PBAbilities,:NOGUARD)
          encount=(encount*2)
        end
      end
    end
    return nil if rand(180*16)>=encount
    encpoke=pbEncounteredPokemon(enctype)
    if encpoke && firstpoke && !firstpoke.isEgg?
      if isConst?(firstpoke.ability,PBAbilities,:INTIMIDATE) ||
         isConst?(firstpoke.ability,PBAbilities,:KEENEYE)
        if encpoke[1]<=firstpoke.level-5 && rand(2)==0
          encpoke=nil
        end
      end
    end
    return encpoke
  end
end