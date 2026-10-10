module BallHandlers
  IsUnconditional = ItemHandlerHash.new
  ModifyCatchRate = ItemHandlerHash.new
  OnCatch         = ItemHandlerHash.new
  OnFailCatch     = ItemHandlerHash.new

  def self.isUnconditional?(ball,battle,battler)
    return false if !IsUnconditional[ball]
    return IsUnconditional.trigger(ball,battle,battler)
  end

  def self.modifyCatchRate(ball,catchRate,battle,battler)
    return catchRate if !ModifyCatchRate[ball]
    return ModifyCatchRate.trigger(ball,catchRate,battle,battler)
  end

  def self.onCatch(ball,battle,pokemon)
    return if !OnCatch[ball]
    OnCatch.trigger(ball,battle,pokemon)
  end

  def self.onFailCatch(ball,battle,battler)
    return if !OnFailCatch[ball]
    OnFailCatch.trigger(ball,battle,battler)
  end
end



def pbBallTypeToBall(balltype)
  if $BallTypes[balltype]
    ret=getID(PBItems,$BallTypes[balltype])
    return ret if ret!=0
  end
  if $BallTypes[0]
    ret=getID(PBItems,$BallTypes[0])
    return ret if ret!=0
  end
  return getID(PBItems,:POKEBALL)
end

def pbGetBallType(ball)
  ball=getID(PBItems,ball)
  for key in $BallTypes.keys
    return key if isConst?(ball,PBItems,$BallTypes[key])
  end
  return 0
end

################################

$BallTypes={
   0=>:POKEBALL,
   1=>:GREATBALL,
   2=>:SAFARIBALL,
   3=>:ULTRABALL,
   4=>:MASTERBALL,
   5=>:NETBALL,
   6=>:DIVEBALL,
   7=>:NESTBALL,
   8=>:REPEATBALL,
   9=>:TIMERBALL,
   10=>:LUXURYBALL,
   11=>:PREMIERBALL,
   12=>:DUSKBALL,
   13=>:HEALBALL,
   14=>:QUICKBALL,
   15=>:CHERISHBALL,
   16=>:FASTBALL,
   17=>:LEVELBALL,
   18=>:LUREBALL,
   19=>:HEAVYBALL,
   20=>:LOVEBALL,
   21=>:FRIENDBALL,
   22=>:MOONBALL,
   23=>:SPORTBALL
}

BallHandlers::ModifyCatchRate.add(:GREATBALL,proc{|ball,catchRate,battle,battler|
   next (catchRate*3/2).floor
})

BallHandlers::ModifyCatchRate.add(:ULTRABALL,proc{|ball,catchRate,battle,battler|
   next (catchRate*2).floor
})

BallHandlers::IsUnconditional.add(:MASTERBALL,proc{|ball,battle,battler|
   next true
})

BallHandlers::ModifyCatchRate.add(:SAFARIBALL,proc{|ball,catchRate,battle,battler|
   next (catchRate*3/2).floor
})

BallHandlers::ModifyCatchRate.add(:NETBALL,proc{|ball,catchRate,battle,battler|
   catchRate*=3 if battler.pbHasType?(:BUG) || battler.pbHasType?(:WATER)
   next catchRate
})

BallHandlers::ModifyCatchRate.add(:DIVEBALL,proc{|ball,catchRate,battle,battler|
   catchRate=(catchRate*7/2).floor if battle.environment==PBEnvironment::Underwater
   next catchRate
})

BallHandlers::ModifyCatchRate.add(:NESTBALL,proc{|ball,catchRate,battle,battler|
   if battler.level<=40
     catchRate*=[(41-battler.level)/10,1].max
   end
   next catchRate
})

BallHandlers::ModifyCatchRate.add(:REPEATBALL,proc{|ball,catchRate,battle,battler|
   catchRate*=3 if battle.pbPlayer.owned[battler.species]
   next catchRate
})

BallHandlers::ModifyCatchRate.add(:TIMERBALL,proc{|ball,catchRate,battle,battler|
   multiplier=[1+(0.3*battle.turncount),4].min
   catchRate*=multiplier
   next catchRate
})

BallHandlers::ModifyCatchRate.add(:DUSKBALL,proc{|ball,catchRate,battle,battler|
   catchRate*=7/2 if PBDayNight.isNight?
   next catchRate
})

BallHandlers::OnCatch.add(:HEALBALL,proc{|ball,battle,pokemon|
   pokemon.heal
})

BallHandlers::ModifyCatchRate.add(:QUICKBALL,proc{|ball,catchRate,battle,battler|
   catchRate*=5 if battle.turncount<=1
   next catchRate
})

BallHandlers::ModifyCatchRate.add(:FASTBALL,proc{|ball,catchRate,battle,battler|
   dexdata=pbOpenDexData
   pbDexDataOffset(dexdata,battler.species,13)
   basespeed=dexdata.fgetb
   dexdata.close
   catchRate*=4 if basespeed>=100
   next [catchRate,255].min
})

BallHandlers::ModifyCatchRate.add(:LEVELBALL,proc{|ball,catchRate,battle,battler|
   pbattler=battle.battlers[0].level
   pbattler=battle.battlers[2].level if battle.battlers[2] &&
                                        battle.battlers[2].level>pbattler
   if pbattler>=battler.level*4
     catchRate*=8
   elsif pbattler>=battler.level*2
     catchRate*=4
   elsif pbattler>battler.level
     catchRate*=2
   end
   next [catchRate,255].min
})

BallHandlers::ModifyCatchRate.add(:LUREBALL,proc{|ball,catchRate,battle,battler|
   catchRate*=3 if $PokemonTemp.encounterType==EncounterTypes::OldRod ||
                   $PokemonTemp.encounterType==EncounterTypes::GoodRod ||
                   $PokemonTemp.encounterType==EncounterTypes::SuperRod
   next [catchRate,255].min
})

BallHandlers::ModifyCatchRate.add(:HEAVYBALL,proc{|ball,catchRate,battle,battler|
   weight=battler.weight
   if weight>=4096
     catchRate+=40
   elsif weight>=3072
     catchRate+=30
   elsif weight>=2048
     catchRate+=20
   else
     catchRate-=20
   end
   catchRate=[catchRate,1].max
   next [catchRate,255].min
})

BallHandlers::ModifyCatchRate.add(:LOVEBALL,proc{|ball,catchRate,battle,battler|
   pbattler=battle.battlers[0]
   pbattler2=battle.battlers[2] if battle.battlers[2]
   if pbattler.species==battler.species &&
      ((battler.gender==0 && pbattler.gender==1) ||
      (battler.gender==1 && pbattler.gender==0))
     catchRate*=8
   elsif pbattler2 && pbattler2.species==battler.species &&
      ((battler.gender==0 && pbattler2.gender==1) ||
       (battler.gender==1 && pbattler2.gender==0))
     catchRate*=8
   end
   next [catchRate,255].min
})

BallHandlers::OnCatch.add(:FRIENDBALL,proc{|ball,battle,pokemon|
   pokemon.happiness=200
})

BallHandlers::ModifyCatchRate.add(:MOONBALL,proc{|ball,catchRate,battle,battler|
   if isConst?(battler.species,PBSpecies,:NIDORANfE) ||
      isConst?(battler.species,PBSpecies,:NIDORINA) ||
      isConst?(battler.species,PBSpecies,:NIDOQUEEN) ||
      isConst?(battler.species,PBSpecies,:NIDORANmA) ||
      isConst?(battler.species,PBSpecies,:NIDORINO) ||
      isConst?(battler.species,PBSpecies,:NIDOKING) ||
      isConst?(battler.species,PBSpecies,:CLEFFA) ||
      isConst?(battler.species,PBSpecies,:CLEFAIRY) ||
      isConst?(battler.species,PBSpecies,:CLEFABLE) ||
      isConst?(battler.species,PBSpecies,:IGGLYBUFF) ||
      isConst?(battler.species,PBSpecies,:JIGGLYPUFF) ||
      isConst?(battler.species,PBSpecies,:WIGGLYTUFF) ||
      isConst?(battler.species,PBSpecies,:SKITTY) ||
      isConst?(battler.species,PBSpecies,:DELCATTY) ||
      isConst?(battler.species,PBSpecies,:MUNNA) ||
      isConst?(battler.species,PBSpecies,:MUSHARNA)
     catchRate*=4
   end
   next [catchRate,255].min
})

BallHandlers::ModifyCatchRate.add(:SPORTBALL,proc{|ball,catchRate,battle,battler|
   next (catchRate*3/2).floor
})