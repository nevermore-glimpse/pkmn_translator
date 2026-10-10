def pbEggGenerated?
  return false if pbDayCareDeposited!=2
  return $PokemonGlobal.daycareEgg==1
end

def pbDayCareDeposited
  ret=0
  for i in 0...2
    ret+=1 if $PokemonGlobal.daycare[i][0]
  end
  return ret
end

def pbDayCareDeposit(index)
  for i in 0...2
    if !$PokemonGlobal.daycare[i][0]
      $PokemonGlobal.daycare[i][0]=$Trainer.party[index]
      $PokemonGlobal.daycare[i][1]=$Trainer.party[index].level
      $PokemonGlobal.daycare[i][0].heal
      $Trainer.party[index]=nil
      $Trainer.party.compact!
      $PokemonGlobal.daycareEgg=0
      $PokemonGlobal.daycareEggSteps=0
      return
    end
  end
  raise _INTL("No room to deposit a Pokémon") 
end

def pbDayCareGetLevelGain(index,nameVariable,levelVariable)
  pkmn=$PokemonGlobal.daycare[index][0]
  return false if !pkmn
  $game_variables[nameVariable]=pkmn.name
  $game_variables[levelVariable]=pkmn.level-$PokemonGlobal.daycare[index][1]
  return true
end

def pbDayCareGetDeposited(index,nameVariable,costVariable)
  for i in 0...2
    if (index<0||i==index) && $PokemonGlobal.daycare[i][0]
      cost=$PokemonGlobal.daycare[i][0].level-$PokemonGlobal.daycare[i][1]
      cost+=1
      cost*=100
      $game_variables[costVariable]=cost if costVariable>=0
      $game_variables[nameVariable]=$PokemonGlobal.daycare[i][0].name if nameVariable>=0
      return
    end
  end
  raise _INTL("Can't find deposited Pokémon")
end

def pbIsDitto?(pokemon)
  dexdata=pbOpenDexData
  pbDexDataOffset(dexdata,pokemon.species,31)
  compat10=dexdata.fgetb
  compat11=dexdata.fgetb
  dexdata.close
  return isConst?(compat10,PBEggGroups,:Ditto) ||
         isConst?(compat11,PBEggGroups,:Ditto)
end

def pbDayCareCompatibleGender(pokemon1,pokemon2)
  if (pokemon1.isFemale? && pokemon2.isMale?) ||
     (pokemon1.isMale? && pokemon2.isFemale?)
    return true
  end
  ditto1=pbIsDitto?(pokemon1)
  ditto2=pbIsDitto?(pokemon2)
  return true if ditto1 && !ditto2
  return true if ditto2 && !ditto1
  return false
end

def pbDayCareGetCompat
  if pbDayCareDeposited==2
    pokemon1=$PokemonGlobal.daycare[0][0]
    pokemon2=$PokemonGlobal.daycare[1][0]
    return 0 if (pokemon1.isShadow? rescue false)
    return 0 if (pokemon2.isShadow? rescue false)
    # Insert code here if certain forms of certain species cannot breed
    dexdata=pbOpenDexData
    pbDexDataOffset(dexdata,pokemon1.species,31)
    compat10=dexdata.fgetb
    compat11=dexdata.fgetb
    pbDexDataOffset(dexdata,pokemon2.species,31)
    compat20=dexdata.fgetb
    compat21=dexdata.fgetb
    dexdata.close
    if !isConst?(compat10,PBEggGroups,:Undiscovered) &&
       !isConst?(compat11,PBEggGroups,:Undiscovered) &&
       !isConst?(compat20,PBEggGroups,:Undiscovered) &&
       !isConst?(compat21,PBEggGroups,:Undiscovered)
      if compat10==compat20 || compat11==compat20 ||
         compat10==compat21 || compat11==compat21 ||
         isConst?(compat10,PBEggGroups,:Ditto) ||
         isConst?(compat11,PBEggGroups,:Ditto) ||
         isConst?(compat20,PBEggGroups,:Ditto) ||
         isConst?(compat21,PBEggGroups,:Ditto)
        if pbDayCareCompatibleGender(pokemon1,pokemon2)
          ret=1
          ret+=1 if pokemon1.species==pokemon2.species
          ret+=1 if pokemon1.trainerID!=pokemon2.trainerID
          return ret
        end
      end
    end
  end
  return 0
end

def pbDayCareGetCompatibility(variable)
  $game_variables[variable]=pbDayCareGetCompat
end

def pbDayCareWithdraw(index)
  if !$PokemonGlobal.daycare[index][0]
    raise _INTL("There's no Pokémon here...")
  elsif $Trainer.party.length>=6
    raise _INTL("Can't store the Pokémon...")
  else
    $Trainer.party[$Trainer.party.length]=$PokemonGlobal.daycare[index][0]
    $PokemonGlobal.daycare[index][0]=nil
    $PokemonGlobal.daycare[index][1]=0
    $PokemonGlobal.daycareEgg=0
  end  
end

def pbDayCareChoose(text,variable)
  count=pbDayCareDeposited
  if count==0
    raise _INTL("There's no Pokémon here...")
  elsif count==1
    $game_variables[variable]=$PokemonGlobal.daycare[0][0] ? 0 : 1
  else
    choices=[]
    for i in 0...2
      pokemon=$PokemonGlobal.daycare[i][0]
      if pokemon.isMale?
        choices.push(_ISPRINTF("{1:s} (♂, Lv{2:d})",pokemon.name,pokemon.level))
      elsif pokemon.isFemale?
        choices.push(_ISPRINTF("{1:s} (♀, Lv{2:d})",pokemon.name,pokemon.level))
      else
        choices.push(_ISPRINTF("{1:s} (Lv{2:d})",pokemon.name,pokemon.level))
      end
    end
    choices.push(_INTL("CANCEL"))
    command=Kernel.pbMessage(text,choices,choices.length)
    $game_variables[variable]=(command==2) ? -1 : command
  end
end

def pbDayCareGenerateEgg
  return if pbDayCareDeposited!=2
  if $Trainer.party.length>=6
    raise _INTL("Can't store the egg")
  end
  pokemon0=$PokemonGlobal.daycare[0][0]
  pokemon1=$PokemonGlobal.daycare[1][0]
  mother=nil
  father=nil
  babyspecies=0
  ditto0=pbIsDitto?(pokemon0)
  ditto1=pbIsDitto?(pokemon1)
  if pokemon0.isFemale? || ditto0
    babyspecies=(ditto0) ? pokemon1.species : pokemon0.species
    mother=pokemon0
    father=pokemon1
  else
    babyspecies=(ditto1) ? pokemon0.species : pokemon1.species
    mother=pokemon1
    father=pokemon0
  end
  babyspecies=pbGetBabySpecies(babyspecies,mother.item,father.item)
  if isConst?(babyspecies,PBSpecies,:MANAPHY) && hasConst?(PBSpecies,:PHIONE)
    babyspecies=getConst(PBSpecies,:PHIONE)
  elsif (isConst?(babyspecies,PBSpecies,:NIDORANfE) && hasConst?(PBSpecies,:NIDORANmA)) ||
        (isConst?(babyspecies,PBSpecies,:NIDORANmA) && hasConst?(PBSpecies,:NIDORANfE))
    babyspecies=[getConst(PBSpecies,:NIDORANmA),
                 getConst(PBSpecies,:NIDORANfE)][rand(2)]
  elsif (isConst?(babyspecies,PBSpecies,:VOLBEAT) && hasConst?(PBSpecies,:ILLUMISE)) ||
        (isConst?(babyspecies,PBSpecies,:ILLUMISE) && hasConst?(PBSpecies,:VOLBEAT))
    babyspecies=[getConst(PBSpecies,:VOLBEAT),
                 getConst(PBSpecies,:ILLUMISE)][rand(2)]
  end
  # Generate egg
  egg=PokeBattle_Pokemon.new(babyspecies,EGGINITIALLEVEL,$Trainer)
  # Randomise personal ID
  pid=rand(65536)
  pid|=(rand(65536)<<16)
  egg.personalID=pid
  # Inheriting form
  if isConst?(babyspecies,PBSpecies,:BURMY) ||
     isConst?(babyspecies,PBSpecies,:SHELLOS) ||
     isConst?(babyspecies,PBSpecies,:BASCULIN) ||
     isConst?(babyspecies,PBSpecies,:FLABEBE) ||
     isConst?(babyspecies,PBSpecies,:PUMPKABOO) ||
     isConst?(babyspecies,PBSpecies,:ORICORIO) ||
     isConst?(babyspecies,PBSpecies,:MINIOR)
    egg.form=mother.form
  end
  # Inheriting Moves
  moves=[]
  othermoves=[] 
  movefather=father; movemother=mother
  if pbIsDitto?(movefather) && !mother.isFemale?
    movefather=mother; movemother=father
  end
  # Initial Moves
  initialmoves=egg.getMoveList
  for k in initialmoves
    if k[0]<=EGGINITIALLEVEL
      moves.push(k[1])
    else
      othermoves.push(k[1]) if mother.hasMove?(k[1]) && father.hasMove?(k[1])
    end
  end
  # Inheriting Natural Moves
  for move in othermoves
    moves.push(move)
  end
  # Inheriting Machine Moves
  if !USENEWBATTLEMECHANICS
    for i in 0...$ItemData.length
      next if !$ItemData[i]
      atk=$ItemData[i][ITEMMACHINE]
      next if !atk || atk==0
      if egg.isCompatibleWithMove?(atk)
        moves.push(atk) if movefather.hasMove?(atk)
      end
    end
  end
  # Inheriting Egg Moves
  if movefather.isMale?
    pbRgssOpen("Data/eggEmerald.dat","rb"){|f|
       f.pos=(egg.fSpecies-1)*8
       offset=f.fgetdw
       length=f.fgetdw
       if length>0
         f.pos=offset
         i=0; loop do break unless i<length
           atk=f.fgetw
           moves.push(atk) if movefather.hasMove?(atk)
           i+=1
         end
       end
    }
  end
  if USENEWBATTLEMECHANICS
    pbRgssOpen("Data/eggEmerald.dat","rb"){|f|
       f.pos=(egg.fSpecies-1)*8
       offset=f.fgetdw
       length=f.fgetdw
       if length>0
         f.pos=offset
         i=0; loop do break unless i<length
           atk=f.fgetw
           moves.push(atk) if movemother.hasMove?(atk)
           i+=1
         end
       end
    }
  end
  # Volt Tackle
  lightball=false
  if (isConst?(father.species,PBSpecies,:PIKACHU) || 
      isConst?(father.species,PBSpecies,:RAICHU)) && 
      isConst?(father.item,PBItems,:LIGHTBALL)
    lightball=true
  end
  if (isConst?(mother.species,PBSpecies,:PIKACHU) || 
      isConst?(mother.species,PBSpecies,:RAICHU)) && 
      isConst?(mother.item,PBItems,:LIGHTBALL)
    lightball=true
  end
  if lightball && isConst?(babyspecies,PBSpecies,:PICHU) &&
     hasConst?(PBMoves,:VOLTTACKLE)
    moves.push(getConst(PBMoves,:VOLTTACKLE))
  end
  moves|=[] # remove duplicates
  # Assembling move list
  finalmoves=[]
  listend=moves.length-4
  listend=0 if listend<0
  j=0
  for i in listend..listend+3
    moveid=(i>=moves.length) ? 0 : moves[i]
    finalmoves[j]=PBMove.new(moveid)
    j+=1
  end 
  # Inheriting Individual Values
  ivs=[]
  for i in 0...6
    ivs[i]=rand(32)
  end
  ivinherit=[]
  for i in 0...2
    parent=[mother,father][i]
    ivinherit[i]=PBStats::HP if isConst?(parent.item,PBItems,:POWERWEIGHT)
    ivinherit[i]=PBStats::ATTACK if isConst?(parent.item,PBItems,:POWERBRACER)
    ivinherit[i]=PBStats::DEFENSE if isConst?(parent.item,PBItems,:POWERBELT)
    ivinherit[i]=PBStats::SPEED if isConst?(parent.item,PBItems,:POWERANKLET)
    ivinherit[i]=PBStats::SPATK if isConst?(parent.item,PBItems,:POWERLENS)
    ivinherit[i]=PBStats::SPDEF if isConst?(parent.item,PBItems,:POWERBAND)
  end
  num=0; r=rand(2)
  for i in 0...2
    if ivinherit[r]!=nil
      parent=[mother,father][r]
      ivs[ivinherit[r]]=parent.iv[ivinherit[r]]
      num+=1
      break
    end
    r=(r+1)%2
  end
  stats=[PBStats::HP,PBStats::ATTACK,PBStats::DEFENSE,
         PBStats::SPEED,PBStats::SPATK,PBStats::SPDEF]
  limit=(USENEWBATTLEMECHANICS && (isConst?(mother.item,PBItems,:DESTINYKNOT) ||
         isConst?(father.item,PBItems,:DESTINYKNOT))) ? 5 : 3
  loop do
    freestats=[]
    for i in stats
      freestats.push(i) if !ivinherit.include?(i)
    end
    break if freestats.length==0
    r=freestats[rand(freestats.length)]
    parent=[mother,father][rand(2)]
    ivs[r]=parent.iv[r]
    ivinherit.push(r)
    num+=1
    break if num>=limit
  end
  # Inheriting nature
  newnatures=[]
  newnatures.push(mother.nature) if isConst?(mother.item,PBItems,:EVERSTONE)
  newnatures.push(father.nature) if isConst?(father.item,PBItems,:EVERSTONE)
  if newnatures.length>0
    egg.setNature(newnatures[rand(newnatures.length)])
  end
  # Masuda method and Shiny Charm
  shinyretries=0
  shinyretries+=5 if father.language!=mother.language
  shinyretries+=2 if hasConst?(PBItems,:SHINYCHARM) &&
                     $PokemonBag.pbHasItem?(:SHINYCHARM)
  if shinyretries>0
    for i in 0...shinyretries
      break if egg.isShiny?
      egg.personalID=rand(65536)|(rand(65536)<<16)
    end
  end
  # Inheriting ability from the mother
  if (!ditto0 && !ditto1)
    if mother.hasHiddenAbility?
      egg.setAbility(mother.abilityIndex) if rand(10)<6
    else
      if rand(10)<8
        egg.setAbility(mother.abilityIndex)
      else
        egg.setAbility((mother.abilityIndex+1)%2)
      end
    end
  elsif ((!ditto0 && ditto1) || (!ditto1 && ditto0)) && USENEWBATTLEMECHANICS
    parent=(!ditto0) ? mother : father
    if parent.hasHiddenAbility?
      egg.setAbility(parent.abilityIndex) if rand(10)<6
    end
  end
  # Inheriting Poké Ball from the mother
  if mother.isFemale? &&
     !isConst?(pbBallTypeToBall(mother.ballused),PBItems,:MASTERBALL) &&
     !isConst?(pbBallTypeToBall(mother.ballused),PBItems,:CHERISHBALL)
    egg.ballused=mother.ballused
  end
  egg.iv[0]=ivs[0]
  egg.iv[1]=ivs[1]
  egg.iv[2]=ivs[2]
  egg.iv[3]=ivs[3]
  egg.iv[4]=ivs[4]
  egg.iv[5]=ivs[5]
  egg.moves[0]=finalmoves[0]
  egg.moves[1]=finalmoves[1]
  egg.moves[2]=finalmoves[2]
  egg.moves[3]=finalmoves[3]
  egg.calcStats
  egg.obtainText=_INTL("Day-Care Couple")
  egg.name=_INTL("Egg")
  dexdata=pbOpenDexData
  pbDexDataOffset(dexdata,babyspecies,21)
  eggsteps=dexdata.fgetw
  dexdata.close
  egg.eggsteps=eggsteps
  if rand(65536)<POKERUSCHANCE
    egg.givePokerus
  end
  $Trainer.party[$Trainer.party.length]=egg
end

Events.onStepTaken+=proc {|sender,e|
   next if !$Trainer
   deposited=pbDayCareDeposited
   if deposited==2 && $PokemonGlobal.daycareEgg==0
     $PokemonGlobal.daycareEggSteps=0 if !$PokemonGlobal.daycareEggSteps
     $PokemonGlobal.daycareEggSteps+=1
     if $PokemonGlobal.daycareEggSteps==256
       $PokemonGlobal.daycareEggSteps=0
       compatval=[0,20,50,70][pbDayCareGetCompat]
       if hasConst?(PBItems,:OVALCHARM) && $PokemonBag.pbHasItem?(:OVALCHARM)
         compatval=[0,40,80,88][pbDayCareGetCompat]
       end
       rnd=rand(100)
       if rnd<compatval
         # Egg is generated
         $PokemonGlobal.daycareEgg=1
       end
     end
   end
   for i in 0...2
     pkmn=$PokemonGlobal.daycare[i][0]
     next if !pkmn
     maxexp=PBExperience.pbGetMaxExperience(pkmn.growthrate)
     if pkmn.exp<maxexp
       oldlevel=pkmn.level
       pkmn.exp+=1
       if pkmn.level!=oldlevel
         pkmn.calcStats
         movelist=pkmn.getMoveList
         for i in movelist
           pkmn.pbLearnMove(i[1]) if i[0]==pkmn.level       # Learned a new move
         end
       end
     end
   end
}