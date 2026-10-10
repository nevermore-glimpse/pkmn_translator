#===============================================================================
# Save type data to PBS file
#===============================================================================
def pbSaveTypes
  return if (PBTypes.maxValue rescue 0)==0
  File.open("PBS/types.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for i in 0..(PBTypes.maxValue rescue 25)
      name = PBTypes.getName(i) rescue nil
      next if !name || name==""
      constname = getConstantName(PBTypes,i) rescue pbGetTypeConst(i)
      f.write(sprintf("[%d]\r\n",i))
      f.write(sprintf("Name=%s\r\n",name))
      f.write(sprintf("InternalName=%s\r\n",constname))
      if (PBTypes.isPseudoType?(i) rescue isConst?(i,PBTypes,QMARKS))
        f.write("IsPseudoType=true\r\n")
      end
      if (PBTypes.isSpecialType?(i) rescue pbIsOldSpecialType?(i))
        f.write("IsSpecialType=true\r\n")
      end
      weak   = []
      resist = []
      immune = []
      for j in 0..(PBTypes.maxValue rescue 25)
        cname = getConstantName(PBTypes,j) rescue pbGetTypeConst(j)
        next if !cname || cname==""
        eff = PBTypes.getEffectiveness(j,i)
        weak.push(cname) if eff==4
        resist.push(cname) if eff==1
        immune.push(cname) if eff==0
      end
      f.write("Weaknesses="+weak.join(",")+"\r\n") if weak.length>0
      f.write("Resistances="+resist.join(",")+"\r\n") if resist.length>0
      f.write("Immunities="+immune.join(",")+"\r\n") if immune.length>0
      f.write("\r\n")
    end
  }
end



#===============================================================================
# Save ability data to PBS file
#===============================================================================
def pbSaveAbilities
  File.open("PBS/abilities.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for i in 1..(PBAbilities.maxValue rescue PBAbilities.getCount-1 rescue pbGetMessageCount(MessageTypes::Abilities)-1)
      abilname = getConstantName(PBAbilities,i) rescue pbGetAbilityConst(i)
      next if !abilname || abilname==""
      name = pbGetMessage(MessageTypes::Abilities,i)
      next if !name || name==""
      f.write(sprintf("%d,%s,%s,%s\r\n",i,csvquote(abilname),csvquote(name),
        csvquote(pbGetMessage(MessageTypes::AbilityDescs,i))))
    end
  }
end



#===============================================================================
# Save move data to PBS file
#===============================================================================
def pbSaveMoveData
  return if !pbRgssExists?("Data/moves.dat")
  File.open("PBS/moves.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for i in 1..(PBMoves.maxValue rescue PBMoves.getCount-1 rescue pbGetMessageCount(MessageTypes::Moves)-1)
      moveconst = getConstantName(PBMoves,i) rescue pbGetMoveConst(i) rescue nil
      next if !moveconst || moveconst==""
      movename = pbGetMessage(MessageTypes::Moves,i)
      movedata = PBMoveData.new(i)
      flags = ""
      flags += "a" if (movedata.flags&0x00001)!=0
      flags += "b" if (movedata.flags&0x00002)!=0
      flags += "c" if (movedata.flags&0x00004)!=0
      flags += "d" if (movedata.flags&0x00008)!=0
      flags += "e" if (movedata.flags&0x00010)!=0
      flags += "f" if (movedata.flags&0x00020)!=0
      flags += "g" if (movedata.flags&0x00040)!=0
      flags += "h" if (movedata.flags&0x00080)!=0
      flags += "i" if (movedata.flags&0x00100)!=0
      flags += "j" if (movedata.flags&0x00200)!=0
      flags += "k" if (movedata.flags&0x00400)!=0
      flags += "l" if (movedata.flags&0x00800)!=0
      flags += "m" if (movedata.flags&0x01000)!=0
      flags += "n" if (movedata.flags&0x02000)!=0
      flags += "o" if (movedata.flags&0x04000)!=0
      flags += "p" if (movedata.flags&0x08000)!=0
      f.write(sprintf("%d,%s,%s,%03X,%d,%s,%s,%d,%d,%d,%02X,%d,%s,%s\r\n",
         i,csvquote(moveconst),csvquote(movename),
         movedata.function,
         movedata.basedamage,
         csvquote((getConstantName(PBTypes,movedata.type) rescue pbGetTypeConst(movedata.type) rescue "")),
         csvquote(["Physical","Special","Status"][movedata.category]),
         movedata.accuracy,
         movedata.totalpp,
         movedata.addlEffect,
         movedata.target,
         movedata.priority,
         flags,
         csvquote(pbGetMessage(MessageTypes::MoveDescriptions,i))))
    end
  }
end



#===============================================================================
# Save map connection data to PBS file
#===============================================================================
def normalizeConnectionPoint(conn)
  ret = conn.clone
  if conn[1]<0 && conn[4]<0
  elsif conn[1]<0 || conn[4]<0
    ret[4] = -conn[1]
    ret[1] = -conn[4]
  end
  if conn[2]<0 && conn[5]<0
  elsif conn[2]<0 || conn[5]<0
    ret[5] = -conn[2]
    ret[2] = -conn[5]
  end
  return ret
end

def writeConnectionPoint(map1,x1,y1,map2,x2,y2)
  dims1 = MapFactoryHelper.getMapDims(map1)
  dims2 = MapFactoryHelper.getMapDims(map2)
  if x1==0 && x2==dims2[0]
    return sprintf("%d,West,%d,%d,East,%d\r\n",map1,y1,map2,y2)
  elsif y1==0 && y2==dims2[1]
    return sprintf("%d,North,%d,%d,South,%d\r\n",map1,x1,map2,x2)
  elsif x1==dims1[0] && x2==0
    return sprintf("%d,East,%d,%d,West,%d\r\n",map1,y1,map2,y2)
  elsif y1==dims1[1] && y2==0
    return sprintf("%d,South,%d,%d,North,%d\r\n",map1,x1,map2,x2)
  else
    return sprintf("%d,%d,%d,%d,%d,%d\r\n",map1,x1,y1,map2,x2,y2)
  end
end

def pbSerializeConnectionData(conndata,mapinfos)
  File.open("PBS/connections.txt","wb"){|f|
    for conn in conndata
      if mapinfos
        # Skip if map no longer exists
        next if !mapinfos[conn[0]] || !mapinfos[conn[3]]
        f.write(sprintf("# %s (%d) - %s (%d)\r\n",
           mapinfos[conn[0]] ? mapinfos[conn[0]].name : "???",conn[0],
           mapinfos[conn[3]] ? mapinfos[conn[3]].name : "???",conn[3]))
      end
      if conn[1].is_a?(String) || conn[4].is_a?(String)
        f.write(sprintf("%d,%s,%d,%d,%s,%d\r\n",conn[0],conn[1],
           conn[2],conn[3],conn[4],conn[5]))
      else
        ret = normalizeConnectionPoint(conn)
        f.write(writeConnectionPoint(ret[0],ret[1],ret[2],ret[3],ret[4],ret[5]))
      end
    end
  }
  save_data(conndata,"Data/connections.dat")
end

def pbSaveConnectionData
  data = load_data("Data/connections.dat") rescue nil
  return if !data
  pbSerializeConnectionData(data,pbLoadRxData("Data/MapInfos"))
end



#===============================================================================
# Save metadata data to PBS file
#===============================================================================
def pbSerializeMetadata(metadata,mapinfos)
  save_data(metadata,"Data/metadata.dat")
  File.open("PBS/metadata.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for i in 0...metadata.length
      next if !metadata[i]
      f.write("\#-------------------------------\r\n")
      f.write(sprintf("[%03d]\r\n",i))
      if i==0
        types = PokemonMetadata::GlobalTypes
      else
        if mapinfos && mapinfos[i]
          f.write(sprintf("# %s\r\n",mapinfos[i].name))
        end
        types = PokemonMetadata::NonGlobalTypes
      end
      for key in types.keys
        schema = types[key]
        record = metadata[i][schema[0]]
        next if record==nil
        f.write(sprintf("%s=",key))
        pbWriteCsvRecord(record,f,schema)
        f.write(sprintf("\r\n"))
      end
    end
  }
end

def pbSaveMetadata
  data = load_data("Data/metadata.dat") rescue nil
  return if !data
  pbSerializeMetadata(data,pbLoadRxData("Data/MapInfos"))
end



#===============================================================================
# Save item data to PBS file
#===============================================================================
def pbSaveItems
  itemData = readItemList("Data/items.dat") rescue nil
  return if !itemData || itemData.length==0
  File.open("PBS/items.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for i in 0...itemData.length
      next if !itemData[i]
      data = itemData[i]
      cname = getConstantName(PBItems,i) rescue sprintf("ITEM%03d",i)
      next if !cname || cname=="" || data[0]==0
      machine = ""
      if data[ITEMMACHINE]>0
        machine = getConstantName(PBMoves,data[ITEMMACHINE]) rescue pbGetMoveConst(data[ITEMMACHINE]) rescue ""
      end
      f.write(sprintf("%d,%s,%s,%s,%d,%d,%s,%d,%d,%d,%s\r\n",
         data[ITEMID],csvquote(cname),csvquote(data[ITEMNAME]),
         csvquote(data[ITEMPLURAL]),data[ITEMPOCKET],data[ITEMPRICE],
         csvquote(data[ITEMDESC]),data[ITEMUSE],data[ITEMBATTLEUSE],
         data[ITEMTYPE],csvquote(machine)))
    end
  }
end



#===============================================================================
# Save berry plant data to PBS file
#===============================================================================
def pbSaveBerryPlants
  berryPlantData = nil
  pbRgssOpen("Data/berryplants.dat","rb"){|f|
    berryPlantData = Marshal.load(f)
  }
  return if !berryPlantData || berryPlantData.length==0
  File.open("PBS/berryplants.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    f.write("\# "+_INTL("See the documentation on the wiki to learn how to edit this file."))
    f.write("\r\n")
    f.write("\#-------------------------------\r\n")
    for i in 0...berryPlantData.length
      next if !berryPlantData[i]
      data = berryPlantData[i]
      cname = getConstantName(PBItems,i) rescue sprintf("ITEM%03d",i)
      next if !cname || cname=="" || i==0
      f.write(sprintf("%s=%d,%d,%d,%d\r\n",
         csvquote(cname),data[0],data[1],data[2],data[3]))
    end
  }
end



#===============================================================================
# Save trainer list data to PBS file
#===============================================================================
def pbSaveTrainerLists
  trainerlists = load_data("Data/trainerlists.dat") rescue nil
  return if !trainerlists
  File.open("PBS/trainerlists.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for tr in trainerlists
      f.write("\#-------------------------------\r\n")
      f.write(((tr[5]) ? "[DefaultTrainerList]" : "[TrainerList]")+"\r\n")
      f.write("Trainers="+tr[3]+"\r\n")
      f.write("Pokemon="+tr[4]+"\r\n")
      f.write("Challenges="+tr[2].join(",")+"\r\n") if !tr[5]
      pbSaveBTTrainers(tr[0],"PBS/"+tr[3])
      pbSaveBattlePokemon(tr[1],"PBS/"+tr[4])
    end
  }
end



#===============================================================================
# Save TM compatibility data to PBS file
#===============================================================================
def pbSaveMachines
  machines = load_data("Data/tm.dat") rescue nil
  return if !machines
  File.open("PBS/tm.txt","wb"){|f|
    for i in 1...machines.length
      Graphics.update if i%50==0
      next if !machines[i]
      movename = getConstantName(PBMoves,i) rescue pbGetMoveConst(i) rescue nil
      next if !movename || movename==""
      f.write("\#-------------------------------\r\n")
      f.write(sprintf("[%s]\r\n",movename))
      x = []
      for j in 0...machines[i].length
        speciesname = getConstantName(PBSpecies,machines[i][j]) rescue pbGetSpeciesConst(machines[i][j]) rescue nil
        next if !speciesname || speciesname==""
        x.push(speciesname)
      end
      f.write(x.join(",")+"\r\n")
    end
  }
end



#===============================================================================
# Save wild encounter data to PBS file
#===============================================================================
def pbSaveEncounterData
  encdata = load_data("Data/encounters.dat") rescue nil
  return if !encdata
  mapinfos = pbLoadRxData("Data/MapInfos")  
  File.open("PBS/encounters.txt","wb"){|f|
    sortedkeys = encdata.keys.sort{|a,b| a<=>b }
    for i in sortedkeys
      if encdata[i]
        e = encdata[i]
        mapname = ""
        if mapinfos[i]
          map = mapinfos[i].name
          mapname = " # #{map}"
        end
        f.write("\#-------------------------------\r\n")
        f.write(sprintf("%03d%s\r\n",i,mapname))
        f.write(sprintf("%d,%d,%d\r\n",e[0][EncounterTypes::Land],
            e[0][EncounterTypes::Cave],e[0][EncounterTypes::Water]))
        for j in 0...e[1].length
          enc = e[1][j]
          next if !enc
          f.write(sprintf("%s\r\n",EncounterTypes::Names[j]))
          for k in 0...EncounterTypes::EnctypeChances[j].length
            encentry = (enc[k]) ? enc[k] : [1,5,5]
            species = getConstantName(PBSpecies,encentry[0]) rescue pbGetSpeciesConst(encentry[0])
            if encentry[1]==encentry[2]
              f.write(sprintf("%s,%d\r\n",species,encentry[1]))
            else
              f.write(sprintf("%s,%d,%d\r\n",species,encentry[1],encentry[2]))
            end
          end
        end
      end
    end
  }
end



#===============================================================================
# Save trainer type data to PBS file
#===============================================================================
def pbSaveTrainerTypes
  data = load_data("Data/trainertypes.dat") rescue nil
  return if !data
  File.open("PBS/trainertypes.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    f.write("\# "+_INTL("See the documentation on the wiki to learn how to edit this file."))
    f.write("\r\n")
    f.write("\#-------------------------------\r\n")
    for i in 0...data.length
      record = data[i]
      if record
        dataline = sprintf("%d,%s,%s,%d,%s,%s,%s,%s,%s,%s\r\n",
           i,record[1],record[2],
           record[3],
           record[4] ? record[4] : "",
           record[5] ? record[5] : "",
           record[6] ? record[6] : "",
           record[7] ? ["Male","Female","Mixed"][record[7]] : "Mixed",
           (record[8]!=record[3]) ? record[8] : "",
           record[9] ? record[9] : "")
        f.write(dataline)
      end
    end
  }
end



#===============================================================================
# Save individual trainer data to PBS file
#===============================================================================
def pbSaveTrainerBattles
  data = load_data("Data/trainers.dat") rescue nil
  return if !data
  File.open("PBS/trainers.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    f.write("\# "+_INTL("See the documentation on the wiki to learn how to edit this file."))
    f.write("\r\n")
    for trainer in data
      trname = getConstantName(PBTrainers,trainer[0]) rescue pbGetTrainerConst(trainer[0]) rescue nil
      next if !trname
      f.write("\#-------------------------------\r\n")
      f.write(sprintf("%s\r\n",trname))
      trainername = trainer[1] ? trainer[1].gsub(/,/,";") : "???"
      if trainer[4]==0
        f.write(sprintf("%s\r\n",trainername))
      else
        f.write(sprintf("%s,%d\r\n",trainername,trainer[4]))
      end
      f.write(sprintf("%d",trainer[3].length))
      for i in 0...8
        itemname = getConstantName(PBItems,trainer[2][i]) rescue pbGetItemConst(trainer[2][i]) rescue nil
        f.write(sprintf(",%s",itemname)) if trainer[2][i]
      end
      f.write("\r\n")
      for poke in trainer[3]
        maxindex = 0
        towrite = []
        thistemp = getConstantName(PBSpecies,poke[TPSPECIES]) rescue pbGetSpeciesConst(poke[TPSPECIES]) rescue ""
        towrite[TPSPECIES]   = thistemp
        towrite[TPLEVEL]     = poke[TPLEVEL].to_s
        thistemp = getConstantName(PBItems,poke[TPITEM]) rescue pbGetItemConst(poke[TPITEM]) rescue ""
        towrite[TPITEM]      = thistemp
        thistemp = getConstantName(PBMoves,poke[TPMOVE1]) rescue pbGetMoveConst(poke[TPMOVE1]) rescue ""
        towrite[TPMOVE1]     = thistemp
        thistemp = getConstantName(PBMoves,poke[TPMOVE2]) rescue pbGetMoveConst(poke[TPMOVE2]) rescue ""
        towrite[TPMOVE2]     = thistemp
        thistemp = getConstantName(PBMoves,poke[TPMOVE3]) rescue pbGetMoveConst(poke[TPMOVE3]) rescue ""
        towrite[TPMOVE3]     = thistemp
        thistemp = getConstantName(PBMoves,poke[TPMOVE4]) rescue pbGetMoveConst(poke[TPMOVE4]) rescue ""
        towrite[TPMOVE4]     = thistemp
        towrite[TPABILITY]   = (poke[TPABILITY]) ? poke[TPABILITY].to_s : ""
        towrite[TPGENDER]    = (poke[TPGENDER]) ? ["M","F"][poke[TPGENDER]] : ""
        towrite[TPFORM]      = (poke[TPFORM] && poke[TPFORM]!=TPDEFAULTS[TPFORM]) ? poke[TPFORM].to_s : ""
        towrite[TPSHINY]     = (poke[TPSHINY]) ? "shiny" : ""
        towrite[TPNATURE]    = (poke[TPNATURE]) ? getConstantName(PBNatures,poke[TPNATURE]) : ""
        towrite[TPIV]        = (poke[TPIV] && poke[TPIV]!=TPDEFAULTS[TPIV]) ? poke[TPIV].to_s : ""
        towrite[TPHAPPINESS] = (poke[TPHAPPINESS] && poke[TPHAPPINESS]!=TPDEFAULTS[TPHAPPINESS]) ? poke[TPHAPPINESS].to_s : ""
        towrite[TPNAME]      = (poke[TPNAME]) ? poke[TPNAME] : ""
        towrite[TPSHADOW]    = (poke[TPSHADOW]) ? "true" : ""
        towrite[TPBALL]      = (poke[TPBALL] && poke[TPBALL]!=TPDEFAULTS[TPBALL]) ? poke[TPBALL].to_s : ""
        for i in 0...towrite.length
          towrite[i] = "" if !towrite[i]
          maxindex = i if towrite[i] && towrite[i]!=""
        end
        for i in 0..maxindex
          f.write(",") if i>0
          f.write(towrite[i])
        end
        f.write("\r\n")
      end
    end
  }
end



#===============================================================================
# Save Town Map data to PBS file
#===============================================================================
def pbSaveTownMap
  mapdata = load_data("Data/townmap.dat") rescue nil
  return if !mapdata
  File.open("PBS/townmap.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for i in 0...mapdata.length
      map = mapdata[i]
      return if !map
      f.write("\#-------------------------------\r\n")
      f.write(sprintf("[%d]\r\n",i))
      rname = pbGetMessage(MessageTypes::RegionNames,i)
      f.write(sprintf("Name=%s\r\nFilename=%s\r\n",
         (rname && rname!="") ? rname : _INTL("Unnamed"),
         csvquote((map[1].is_a?(Array)) ? map[1][0] : map[1])))
      for loc in map[2]
        f.write("Point=")
        pbWriteCsvRecord(loc,f,[nil,"uussUUUU"])
        f.write("\r\n")
      end
    end
  }
end



#===============================================================================
# Save phone message data to PBS file
#===============================================================================
def pbSavePhoneData
  data = load_data("Data/phone.dat") rescue nil
  return if !data
  File.open("PBS/phone.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    f.write("\#-------------------------------\r\n")
    f.write("[<Generics>]\r\n")
    f.write(data.generics.join("\r\n")+"\r\n")
    f.write("\#-------------------------------\r\n")
    f.write("[<BattleRequests>]\r\n")
    f.write(data.battleRequests.join("\r\n")+"\r\n")
    f.write("\#-------------------------------\r\n")
    f.write("[<GreetingsMorning>]\r\n")
    f.write(data.greetingsMorning.join("\r\n")+"\r\n")
    f.write("\#-------------------------------\r\n")
    f.write("[<GreetingsEvening>]\r\n")
    f.write(data.greetingsEvening.join("\r\n")+"\r\n")
    f.write("\#-------------------------------\r\n")
    f.write("[<Greetings>]\r\n")
    f.write(data.greetings.join("\r\n")+"\r\n")
    f.write("\#-------------------------------\r\n")
    f.write("[<Bodies1>]\r\n")
    f.write(data.bodies1.join("\r\n")+"\r\n")
    f.write("\#-------------------------------\r\n")
    f.write("[<Bodies2>]\r\n")
    f.write(data.bodies2.join("\r\n")+"\r\n")
  }
end



#===============================================================================
# Save Pokémon data to PBS file
#===============================================================================
def pbSavePokemonData
  dexdata      = File.open("Data/dexdata.dat","rb") rescue nil
  messages     = Messages.new("Data/messages.dat") rescue nil
  return if !dexdata || !messages
  metrics      = load_data("Data/metrics.dat") rescue nil
  atkdata      = File.open("Data/attacksRS.dat","rb")
  eggEmerald   = File.open("Data/eggEmerald.dat","rb")
  regionaldata = File.open("Data/regionals.dat","rb")
  numRegions   = regionaldata.fgetw
  numDexDatas  = regionaldata.fgetw
  pokedata = File.open("PBS/pokemon.txt","wb") rescue nil
  pokedata.write(0xEF.chr)
  pokedata.write(0xBB.chr)
  pokedata.write(0xBF.chr)
  for i in 1..(PBSpecies.maxValue rescue PBSpecies.getCount-1 rescue messages.getCount(MessageTypes::Species)-1)
    cname       = getConstantName(PBSpecies,i) rescue next
    speciesname = messages.get(MessageTypes::Species,i)
    kind        = messages.get(MessageTypes::Kinds,i)
    entry       = messages.get(MessageTypes::Entries,i)
    formname    = messages.get(MessageTypes::FormNames,i)
    pbDexDataOffset(dexdata,i,2)
    ability1       = dexdata.fgetw
    ability2       = dexdata.fgetw
    color          = dexdata.fgetb
    habitat        = dexdata.fgetb
    type1          = dexdata.fgetb
    type2          = dexdata.fgetb
    basestats = []
    for j in 0...6
      basestats.push(dexdata.fgetb)
    end
    rareness       = dexdata.fgetb
    shape          = dexdata.fgetb
    gender         = dexdata.fgetb
    happiness      = dexdata.fgetb
    growthrate     = dexdata.fgetb
    stepstohatch   = dexdata.fgetw
    effort = []
    for j in 0...6
      effort.push(dexdata.fgetb)
    end
    pbDexDataOffset(dexdata,i,31)
    compat1        = dexdata.fgetb
    compat2        = dexdata.fgetb
    height         = dexdata.fgetw
    weight         = dexdata.fgetw
    pbDexDataOffset(dexdata,i,38)
    baseexp        = dexdata.fgetw
    hiddenability1 = dexdata.fgetw
    hiddenability2 = dexdata.fgetw
    hiddenability3 = dexdata.fgetw
    hiddenability4 = dexdata.fgetw
    item1          = dexdata.fgetw
    item2          = dexdata.fgetw
    item3          = dexdata.fgetw
    incense        = dexdata.fgetw
    pokedata.write("\#-------------------------------\r\n")
    pokedata.write("[#{i}]\r\nName=#{speciesname}\r\n")
    pokedata.write("InternalName=#{cname}\r\n")
    ctype1 = getConstantName(PBTypes,type1) rescue pbGetTypeConst(type1) || pbGetTypeConst(0) || "NORMAL"
    pokedata.write("Type1=#{ctype1}\r\n")
    if type1!=type2
      ctype2 = getConstantName(PBTypes,type2) rescue pbGetTypeConst(type2) || pbGetTypeConst(0) || "NORMAL"
      pokedata.write("Type2=#{ctype2}\r\n")
    end
    pokedata.write("BaseStats=#{basestats[0]},#{basestats[1]},#{basestats[2]},#{basestats[3]},#{basestats[4]},#{basestats[5]}\r\n")
    case gender
    when 0;   pokedata.write("GenderRate=AlwaysMale\r\n")
    when 31;  pokedata.write("GenderRate=FemaleOneEighth\r\n")
    when 63;  pokedata.write("GenderRate=Female25Percent\r\n")
    when 127; pokedata.write("GenderRate=Female50Percent\r\n")
    when 191; pokedata.write("GenderRate=Female75Percent\r\n")
    when 223; pokedata.write("GenderRate=FemaleSevenEighths\r\n")
    when 254; pokedata.write("GenderRate=AlwaysFemale\r\n")
    when 255; pokedata.write("GenderRate=Genderless\r\n")
    end
    pokedata.write("GrowthRate=" + ["Medium","Erratic","Fluctuating","Parabolic","Fast","Slow"][growthrate]+"\r\n")
    pokedata.write("BaseEXP=#{baseexp}\r\n")
    pokedata.write("EffortPoints=#{effort[0]},#{effort[1]},#{effort[2]},#{effort[3]},#{effort[4]},#{effort[5]}\r\n")
    pokedata.write("Rareness=#{rareness}\r\n")
    pokedata.write("Happiness=#{happiness}\r\n")
    pokedata.write("Abilities=")
    if ability1!=0
      cability1 = getConstantName(PBAbilities,ability1) rescue pbGetAbilityConst(ability1)
      pokedata.write("#{cability1}")
      pokedata.write(",") if ability2!=0
    end
    if ability2!=0
      cability2 = getConstantName(PBAbilities,ability2) rescue pbGetAbilityConst(ability2)
      pokedata.write("#{cability2}")
    end
    pokedata.write("\r\n")
    if hiddenability1>0 || hiddenability2>0 || hiddenability3>0 || hiddenability4>0
      pokedata.write("HiddenAbility=")
      needcomma = false
      if hiddenability1>0
        cabilityh = getConstantName(PBAbilities,hiddenability1) rescue pbGetAbilityConst(hiddenability1)
        pokedata.write("#{cabilityh}"); needcomma=true
      end
      if hiddenability2>0
        pokedata.write(",") if needcomma
        cabilityh = getConstantName(PBAbilities,hiddenability2) rescue pbGetAbilityConst(hiddenability2)
        pokedata.write("#{cabilityh}"); needcomma=true
      end
      if hiddenability3>0
        pokedata.write(",") if needcomma
        cabilityh = getConstantName(PBAbilities,hiddenability3) rescue pbGetAbilityConst(hiddenability3)
        pokedata.write("#{cabilityh}"); needcomma=true
      end
      if hiddenability4>0
        pokedata.write(",") if needcomma
        cabilityh = getConstantName(PBAbilities,hiddenability4) rescue pbGetAbilityConst(hiddenability4)
        pokedata.write("#{cabilityh}")
      end
      pokedata.write("\r\n")
    end
    pokedata.write("Moves=")
    offset = atkdata.getOffset(i-1)
    length = atkdata.getLength(i-1)>>1
    atkdata.pos = offset
    movelist = []
    for j in 0...length
      alevel = atkdata.fgetw
      move   = atkdata.fgetw
      movelist.push([j,alevel,move])
    end
    movelist.sort!{|a,b| (a[1]==b[1]) ? a[0]<=>b[0] : a[1]<=>b[1] }
    for j in 0...movelist.length
      alevel = movelist[j][1]
      move   = movelist[j][2]
      pokedata.write(",") if j>0
      cmove = getConstantName(PBMoves,move) rescue pbGetMoveConst(move)
      pokedata.write(sprintf("%d,%s",alevel,cmove))
    end
    pokedata.write("\r\n")
    eggEmerald.pos = (i-1)*8
    offset = eggEmerald.fgetdw
    length = eggEmerald.fgetdw
    if length>0
      pokedata.write("EggMoves=")
      eggEmerald.pos = offset
      first = true
      j = 0; loop do break unless j<length
        atk = eggEmerald.fgetw
        pokedata.write(",") if !first
        break if atk==0
        if atk>0
          cmove = getConstantName(PBMoves,atk) rescue pbGetMoveConst(atk)
          pokedata.write("#{cmove}")
          first = false
        end
        j += 1
      end
      pokedata.write("\r\n")
    end
    comp1 = getConstantName(PBEggGroups,compat1) rescue pbGetEggGroupConst(compat1)
    comp2 = getConstantName(PBEggGroups,compat2) rescue pbGetEggGroupConst(compat2)
    if compat1==compat2
      pokedata.write("Compatibility=#{comp1}\r\n")
    else
      pokedata.write("Compatibility=#{comp1},#{comp2}\r\n")
    end
    pokedata.write("StepsToHatch=#{stepstohatch}\r\n")
    pokedata.write("Height=")
    pokedata.write(sprintf("%.1f",height/10.0)) if height
    pokedata.write("\r\n")
    pokedata.write("Weight=")
    pokedata.write(sprintf("%.1f",weight/10.0)) if weight
    pokedata.write("\r\n")
    colorname = getConstantName(PBColors,color) rescue pbGetColorConst(color)
    pokedata.write("Color=#{colorname}\r\n")
    pokedata.write("Shape=#{shape}\r\n")
    pokedata.write("Habitat="+["","Grassland","Forest","WatersEdge","Sea","Cave","Mountain","RoughTerrain","Urban","Rare"][habitat]+"\r\n") if habitat>0
    regionallist = []
    for region in 0...numRegions
      regionaldata.pos = 4+region*numDexDatas*2+(i*2)
      regionallist.push(regionaldata.fgetw)
    end
    numb = regionallist.size-1
    while (numb>=0) # remove every 0 at end of array 
      (regionallist[numb]==0) ? regionallist.pop : break
      numb -= 1
    end
    if !regionallist.empty?
      pokedata.write("RegionalNumbers="+regionallist[0].to_s)
      for numb in 1...regionallist.size
        pokedata.write(","+regionallist[numb].to_s)
      end
      pokedata.write("\r\n")
    end
    pokedata.write("Kind=#{kind}\r\n")
    pokedata.write("Pokedex=#{entry}\r\n")
    if formname && formname!=""
      pokedata.write("FormName=#{formname}\r\n")
    end
    if item1>0
      citem1 = getConstantName(PBItems,item1) rescue pbGetItemConst(item1)
      pokedata.write("WildItemCommon=#{citem1}\r\n")
    end
    if item2>0
      citem2 = getConstantName(PBItems,item2) rescue pbGetItemConst(item2)
      pokedata.write("WildItemUncommon=#{citem2}\r\n")
    end
    if item3>0
      citem3 = getConstantName(PBItems,item3) rescue pbGetItemConst(item3)
      pokedata.write("WildItemRare=#{citem3}\r\n")
    end
    if metrics
      pokedata.write("BattlerPlayerY=#{metrics[0][i] || 0}\r\n")
      pokedata.write("BattlerEnemyY=#{metrics[1][i] || 0}\r\n")
      pokedata.write("BattlerAltitude=#{metrics[2][i] || 0}\r\n")
    end
    pokedata.write("Evolutions=")
    count = 0
    for form in pbGetEvolvedFormData(i)
      evonib = form[0]
      level  = form[1]
      poke   = form[2]
      next if poke==0 || evonib==PBEvolution::Unknown
      cpoke   = getConstantName(PBSpecies,poke) rescue pbGetSpeciesConst(poke)
      evoname = getConstantName(PBEvolution,evonib) rescue pbGetEvolutionConst(evonib)
      next if !cpoke || cpoke==""
      pokedata.write(",") if count>0
      pokedata.write(sprintf("%s,%s,",cpoke,evoname))
      case PBEvolution::EVOPARAM[evonib]
      when 1
        pokedata.write("#{level}")
      when 2
        clevel = getConstantName(PBItems,level) rescue pbGetItemConst(level)
        pokedata.write("#{clevel}")
      when 3
        clevel = getConstantName(PBMoves,level) rescue pbGetMoveConst(level)
        pokedata.write("#{clevel}")
      when 4
        clevel = getConstantName(PBSpecies,level) rescue pbGetSpeciesConst(level)
        pokedata.write("#{clevel}")
      when 5
        clevel = getConstantName(PBTypes,level) rescue pbGetTypeConst(level)
        pokedata.write("#{clevel}")
      end
      count += 1
    end
    pokedata.write("\r\n")
    if incense>0
      initem = getConstantName(PBItems,incense) rescue pbGetItemConst(incense)
      pokedata.write("Incense=#{initem}\r\n")
    end
    if i%20==0
      Graphics.update
      Win32API.SetWindowText(_INTL("Processing species {1}...",i))
    end
  end
  dexdata.close
  atkdata.close
  eggEmerald.close
  regionaldata.close
  pokedata.close
  Graphics.update
end



#===============================================================================
# Save Pokémon forms data to PBS file
#===============================================================================
def pbSavePokemonFormsData
  dexdata      = File.open("Data/dexdata.dat","rb") rescue nil
  messages     = Messages.new("Data/messages.dat") rescue nil
  return if !dexdata || !messages
  metrics      = load_data("Data/metrics.dat") rescue nil
  atkdata      = File.open("Data/attacksRS.dat","rb")
  eggEmerald   = File.open("Data/eggEmerald.dat","rb")
  pokedata = File.open("PBS/pokemonforms.txt","wb") rescue nil
  pokedata.write(0xEF.chr)
  pokedata.write(0xBB.chr)
  pokedata.write(0xBF.chr)
  m1 = (PBSpecies.maxValue+1 rescue PBSpecies.getCount rescue messages.getCount(MessageTypes::Species))
  m2 = (PBSpecies.maxValueF rescue m1)
  for i in m1..m2
    species,form = pbGetSpeciesFromFSpecies(i)
    next if !species || species==0 || !form || form==0
    cname = getConstantName(PBSpecies,species) rescue next
    origkind    = messages.get(MessageTypes::Kinds,species)
    kind        = messages.get(MessageTypes::Kinds,i)
    kind = nil if kind==origkind || kind==""
    origentry   = messages.get(MessageTypes::Entries,species)
    entry       = messages.get(MessageTypes::Entries,i)
    entry = nil if entry==origentry || entry==""
    formname    = messages.get(MessageTypes::FormNames,i)
    origdata = {}
    pbDexDataOffset(dexdata,species,2)
    origdata["ability1"]       = dexdata.fgetw
    origdata["ability2"]       = dexdata.fgetw
    origdata["color"]          = dexdata.fgetb
    origdata["habitat"]        = dexdata.fgetb
    origdata["type1"]          = dexdata.fgetb
    origdata["type2"]          = dexdata.fgetb
    origdata["basestats"] = []
    for j in 0...6
      origdata["basestats"].push(dexdata.fgetb)
    end
    origdata["rareness"]       = dexdata.fgetb
    origdata["shape"]          = dexdata.fgetb
    origdata["gender"]         = dexdata.fgetb
    origdata["happiness"]      = dexdata.fgetb
    origdata["growthrate"]     = dexdata.fgetb
    origdata["stepstohatch"]   = dexdata.fgetw
    origdata["effort"] = []
    for j in 0...6
      origdata["effort"].push(dexdata.fgetb)
    end
    pbDexDataOffset(dexdata,species,31)
    origdata["compat1"]        = dexdata.fgetb
    origdata["compat2"]        = dexdata.fgetb
    origdata["height"]         = dexdata.fgetw
    origdata["weight"]         = dexdata.fgetw
    pbDexDataOffset(dexdata,species,38)
    origdata["baseexp"]        = dexdata.fgetw
    origdata["hiddenability1"] = dexdata.fgetw
    origdata["hiddenability2"] = dexdata.fgetw
    origdata["hiddenability3"] = dexdata.fgetw
    origdata["hiddenability4"] = dexdata.fgetw
    origdata["item1"]          = dexdata.fgetw
    origdata["item2"]          = dexdata.fgetw
    origdata["item3"]          = dexdata.fgetw
    origdata["incense"]        = dexdata.fgetw
    data = []
    pbDexDataOffset(dexdata,i,2)
    ability1       = dexdata.fgetw
    ability2       = dexdata.fgetw
    color          = dexdata.fgetb; color = nil if color==origdata["color"]
    habitat        = dexdata.fgetb; habitat = nil if habitat==origdata["habitat"]
    type1          = dexdata.fgetb
    type2          = dexdata.fgetb
    basestats = []
    for j in 0...6
      basestats.push(dexdata.fgetb)
    end
    rareness       = dexdata.fgetb; rareness = nil if rareness==origdata["rareness"]
    shape          = dexdata.fgetb; shape = nil if shape==origdata["shape"]
    gender         = dexdata.fgetb; gender = nil if gender==origdata["gender"]
    happiness      = dexdata.fgetb; happiness = nil if happiness==origdata["happiness"]
    growthrate     = dexdata.fgetb; growthrate = nil if growthrate==origdata["growthrate"]
    stepstohatch   = dexdata.fgetw; stepstohatch = nil if stepstohatch==origdata["stepstohatch"]
    effort = []
    for j in 0...6
      effort.push(dexdata.fgetb)
    end
    megastone      = dexdata.fgetw # No nil check
    compat1        = dexdata.fgetb
    compat2        = dexdata.fgetb
    height         = dexdata.fgetw; height = nil if height==origdata["height"]
    weight         = dexdata.fgetw; weight = nil if weight==origdata["weight"]
    unmega         = dexdata.fgetb # No nil check
    baseexp        = dexdata.fgetw; baseexp = nil if baseexp==origdata["baseexp"]
    hiddenability1 = dexdata.fgetw
    hiddenability2 = dexdata.fgetw
    hiddenability3 = dexdata.fgetw
    hiddenability4 = dexdata.fgetw
    item1          = dexdata.fgetw
    item2          = dexdata.fgetw
    item3          = dexdata.fgetw
    incense        = dexdata.fgetw; incense = nil if incense==origdata["incense"]
    megamove       = dexdata.fgetw # No nil check
    megamessage    = dexdata.fgetb # No nil check
    if ability1==origdata["ability1"] && ability2==origdata["ability2"] &&
       hiddenability1==origdata["hiddenability1"] &&
       hiddenability2==origdata["hiddenability2"] &&
       hiddenability3==origdata["hiddenability3"] &&
       hiddenability4==origdata["hiddenability4"]
      ability1 = nil; ability2 = nil
      hiddenability1 = nil; hiddenability2 = nil; hiddenability3 = nil; hiddenability4 = nil
    end
    if type1==origdata["type1"] && type2==origdata["type2"]
      type1 = nil; type2 = nil
    end
    diff = false
    for k in 0...6
      if basestats[k]!=origdata["basestats"][k]
        diff = true; break
      end
    end
    basestats = nil if !diff
    diff = false
    for k in 0...6
      if effort[k]!=origdata["effort"][k]
        diff = true; break
      end
    end
    effort = nil if !diff
    if compat1==origdata["compat1"] && compat2==origdata["compat2"]
      compat1 = nil; compat2 = nil
    end
    if item1==origdata["item1"] && item2==origdata["item2"] && item3==origdata["item3"]
      item1 = nil; item2 = nil; item3 = nil
    end
    pokedata.write("\#-------------------------------\r\n")
    pokedata.write("[#{cname}-#{form}]\r\n")
    pokedata.write("FormName=#{formname}\r\n") if formname!=nil && formname!=""
    if megastone>0
      citem = getConstantName(PBItems,megastone) rescue pbGetItemConst(megastone)
      pokedata.write("MegaStone=#{citem}\r\n")
    end
    if megamove>0
      cmove = getConstantName(PBMoves,megamove) rescue pbGetMoveConst(megamove)
      pokedata.write("MegaMove=#{cmove}\r\n")
    end
    pokedata.write("UnmegaForm=#{unmega}\r\n") if unmega>0
    pokedata.write("MegaMessage=#{megamessage}\r\n") if megamessage>0
    if type1!=nil && type2!=nil
      ctype1 = getConstantName(PBTypes,type1) rescue pbGetTypeConst(type1) || pbGetTypeConst(0) || "NORMAL"
      pokedata.write("Type1=#{ctype1}\r\n")
      if type1!=type2
        ctype2 = getConstantName(PBTypes,type2) rescue pbGetTypeConst(type2) || pbGetTypeConst(0) || "NORMAL"
        pokedata.write("Type2=#{ctype2}\r\n")
      end
    end
    if basestats!=nil
      pokedata.write("BaseStats=#{basestats[0]},#{basestats[1]},#{basestats[2]},#{basestats[3]},#{basestats[4]},#{basestats[5]}\r\n")
    end
    if gender!=nil
      case gender
      when 0;   pokedata.write("GenderRate=AlwaysMale\r\n")
      when 31;  pokedata.write("GenderRate=FemaleOneEighth\r\n")
      when 63;  pokedata.write("GenderRate=Female25Percent\r\n")
      when 127; pokedata.write("GenderRate=Female50Percent\r\n")
      when 191; pokedata.write("GenderRate=Female75Percent\r\n")
      when 223; pokedata.write("GenderRate=FemaleSevenEighths\r\n")
      when 254; pokedata.write("GenderRate=AlwaysFemale\r\n")
      when 255; pokedata.write("GenderRate=Genderless\r\n")
      end
    end
    if growthrate!=nil
      pokedata.write("GrowthRate=" + ["Medium","Erratic","Fluctuating","Parabolic","Fast","Slow"][growthrate]+"\r\n")
    end
    if baseexp!=nil
      pokedata.write("BaseEXP=#{baseexp}\r\n")
    end
    if effort!=nil
      pokedata.write("EffortPoints=#{effort[0]},#{effort[1]},#{effort[2]},#{effort[3]},#{effort[4]},#{effort[5]}\r\n")
    end
    if rareness!=nil
      pokedata.write("Rareness=#{rareness}\r\n")
    end
    if happiness!=nil
      pokedata.write("Happiness=#{happiness}\r\n")
    end
    if ability1!=nil && ability2!=nil
      pokedata.write("Abilities=")
      if ability1!=0
        cability1 = getConstantName(PBAbilities,ability1) rescue pbGetAbilityConst(ability1)
        pokedata.write("#{cability1}")
        pokedata.write(",") if ability2!=0
      end
      if ability2!=0
        cability2 = getConstantName(PBAbilities,ability2) rescue pbGetAbilityConst(ability2)
        pokedata.write("#{cability2}")
      end
      pokedata.write("\r\n")
    end
    if hiddenability1!=nil
      if hiddenability1>0 || hiddenability2>0 || hiddenability3>0 || hiddenability4>0
        pokedata.write("HiddenAbility=")
        needcomma = false
        if hiddenability1>0
          cabilityh = getConstantName(PBAbilities,hiddenability1) rescue pbGetAbilityConst(hiddenability1)
          pokedata.write("#{cabilityh}"); needcomma=true
        end
        if hiddenability2>0
          pokedata.write(",") if needcomma
          cabilityh = getConstantName(PBAbilities,hiddenability2) rescue pbGetAbilityConst(hiddenability2)
          pokedata.write("#{cabilityh}"); needcomma=true
        end
        if hiddenability3>0
          pokedata.write(",") if needcomma
          cabilityh = getConstantName(PBAbilities,hiddenability3) rescue pbGetAbilityConst(hiddenability3)
          pokedata.write("#{cabilityh}"); needcomma=true
        end
        if hiddenability4>0
          pokedata.write(",") if needcomma
          cabilityh = getConstantName(PBAbilities,hiddenability4) rescue pbGetAbilityConst(hiddenability4)
          pokedata.write("#{cabilityh}")
        end
        pokedata.write("\r\n")
      end
    end
    offset = atkdata.getOffset(species-1)
    length = atkdata.getLength(species-1)>>1
    atkdata.pos = offset
    origmoves = []
    for j in 0...length
      alevel = atkdata.fgetw
      move   = atkdata.fgetw
      origmoves.push([j,alevel,move])
    end
    origmoves.sort!{|a,b| (a[1]==b[1]) ? a[0]<=>b[0] : a[1]<=>b[1] }
    offset = atkdata.getOffset(i-1)
    length = atkdata.getLength(i-1)>>1
    atkdata.pos = offset
    movelist = []
    for j in 0...length
      alevel = atkdata.fgetw
      move   = atkdata.fgetw
      movelist.push([j,alevel,move])
    end
    movelist.sort!{|a,b| (a[1]==b[1]) ? a[0]<=>b[0] : a[1]<=>b[1] }
    diff = false
    if movelist.length!=origmoves.length
      diff = true
    else
      for k in 0...movelist.length
        if movelist[k][1]!=origmoves[k][1] || movelist[k][2]!=origmoves[k][2]
          diff = true; break
        end
      end
    end
    if diff
      pokedata.write("Moves=")
      for j in 0...movelist.length
        alevel = movelist[j][1]
        move   = movelist[j][2]
        pokedata.write(",") if j>0
        cmove = getConstantName(PBMoves,move) rescue pbGetMoveConst(move)
        pokedata.write(sprintf("%d,%s",alevel,cmove))
      end
      pokedata.write("\r\n")
    end
    origeggmoves = []
    eggEmerald.pos = (species-1)*8
    offset = eggEmerald.fgetdw
    length = eggEmerald.fgetdw
    if length>0
      eggEmerald.pos = offset
      j = 0; loop do break unless j<length
        atk = eggEmerald.fgetw
        break if atk==0
        origeggmoves.push(atk)
        j += 1
      end
    end
    egglist = []
    eggEmerald.pos = (i-1)*8
    offset = eggEmerald.fgetdw
    length = eggEmerald.fgetdw
    if length>0
      eggEmerald.pos = offset
      j = 0; loop do break unless j<length
        atk = eggEmerald.fgetw
        break if atk==0
        egglist.push(atk)
        j += 1
      end
    end
    diff = false
    if egglist.length!=origeggmoves.length
      diff = true
    else
      for k in 0...egglist.length
        if egglist[k]!=origeggmoves[k]
          diff = true; break
        end
      end
    end
    if diff
      pokedata.write("EggMoves=")
      for k in 0...egglist.length
        atk = egglist[k]
        cmove = getConstantName(PBMoves,atk) rescue pbGetMoveConst(atk)
        pokedata.write("#{cmove}")
        pokedata.write(",") if !k<egglist.length-1
      end
      pokedata.write("\r\n")
    end
    if compat1!=nil && compat2!=nil
      comp1 = getConstantName(PBEggGroups,compat1) rescue pbGetEggGroupConst(compat1)
      comp2 = getConstantName(PBEggGroups,compat2) rescue pbGetEggGroupConst(compat2)
      if compat1==compat2
        pokedata.write("Compatibility=#{comp1}\r\n")
      else
        pokedata.write("Compatibility=#{comp1},#{comp2}\r\n")
      end
    end
    if stepstohatch!=nil
      pokedata.write("StepsToHatch=#{stepstohatch}\r\n")
    end
    if height!=nil
      pokedata.write("Height=")
      pokedata.write(sprintf("%.1f",height/10.0))
      pokedata.write("\r\n")
    end
    if weight!=nil
      pokedata.write("Weight=")
      pokedata.write(sprintf("%.1f",weight/10.0))
      pokedata.write("\r\n")
    end
    if color!=nil
      colorname = getConstantName(PBColors,color) rescue pbGetColorConst(color)
      pokedata.write("Color=#{colorname}\r\n")
    end
    if shape!=nil
      pokedata.write("Shape=#{shape}\r\n")
    end
    if habitat!=nil
      pokedata.write("Habitat="+["","Grassland","Forest","WatersEdge","Sea","Cave","Mountain","RoughTerrain","Urban","Rare"][habitat]+"\r\n") if habitat>0
    end
    if kind!=nil
      pokedata.write("Kind=#{kind}\r\n")
    end
    if entry!=nil
      pokedata.write("Pokedex=#{entry}\r\n")
    end
    if item1!=nil && item2!=nil && item3!=nil
      if item1>0
        citem1 = getConstantName(PBItems,item1) rescue pbGetItemConst(item1)
        pokedata.write("WildItemCommon=#{citem1}\r\n")
      end
      if item2>0
        citem2 = getConstantName(PBItems,item2) rescue pbGetItemConst(item2)
        pokedata.write("WildItemUncommon=#{citem2}\r\n")
      end
      if item3>0
        citem3 = getConstantName(PBItems,item3) rescue pbGetItemConst(item3)
        pokedata.write("WildItemRare=#{citem3}\r\n")
      end
    end
    if metrics
      if metrics[0][i]!=metrics[0][species]
        pokedata.write("BattlerPlayerY=#{metrics[0][i] || 0}\r\n")
      end
      if metrics[1][i]!=metrics[1][species]
        pokedata.write("BattlerEnemyY=#{metrics[1][i] || 0}\r\n")
      end
      if metrics[2][i]!=metrics[2][species]
        pokedata.write("BattlerAltitude=#{metrics[2][i] || 0}\r\n")
      end
    end
    origevos = []
    for form in pbGetEvolvedFormData(species)
      evonib = form[0]
      level  = form[1]
      poke   = form[2]
      next if poke==0 || evonib==PBEvolution::Unknown
      cpoke   = getConstantName(PBSpecies,poke) rescue pbGetSpeciesConst(poke)
      evoname = getConstantName(PBEvolution,evonib) rescue pbGetEvolutionConst(evonib)
      next if !cpoke || cpoke==""
      origevos.push([evonib,level,poke])
    end
    evos = []
    for form in pbGetEvolvedFormData(i)
      evonib = form[0]
      level  = form[1]
      poke   = form[2]
      next if poke==0 || evonib==PBEvolution::Unknown
      cpoke   = getConstantName(PBSpecies,poke) rescue pbGetSpeciesConst(poke)
      evoname = getConstantName(PBEvolution,evonib) rescue pbGetEvolutionConst(evonib)
      next if !cpoke || cpoke==""
      evos.push([evonib,level,poke])
    end
    diff = false
    if evos.length!=origevos.length
      diff = true
    else
      for k in 0...evos.length
        if evos[k][0]!=origevos[k][0] ||
           evos[k][1]!=origevos[k][1] ||
           evos[k][2]!=origevos[k][2]
          diff = true; break
        end
      end
    end
    if diff
      pokedata.write("Evolutions=")
      for k in 0...evos.length
        cpoke   = getConstantName(PBSpecies,poke) rescue pbGetSpeciesConst(poke)
        evoname = getConstantName(PBEvolution,evonib) rescue pbGetEvolutionConst(evonib)
        next if !cpoke || cpoke==""
        pokedata.write(sprintf("%s,%s,",cpoke,evoname))
        case PBEvolution::EVOPARAM[evonib]
        when 1
          pokedata.write("#{level}")
        when 2
          clevel = getConstantName(PBItems,level) rescue pbGetItemConst(level)
          pokedata.write("#{clevel}")
        when 3
          clevel = getConstantName(PBMoves,level) rescue pbGetMoveConst(level)
          pokedata.write("#{clevel}")
        when 4
          clevel = getConstantName(PBSpecies,level) rescue pbGetSpeciesConst(level)
          pokedata.write("#{clevel}")
        when 5
          clevel = getConstantName(PBTypes,level) rescue pbGetTypeConst(level)
          pokedata.write("#{clevel}")
        end
        pokedata.write(",") if k<evos.length-1
      end
      pokedata.write("\r\n")
    end
    if incense!=nil
      if incense>0
        initem = getConstantName(PBItems,incense) rescue pbGetItemConst(incense)
        pokedata.write("Incense=#{initem}\r\n")
      end
    end
    if i%20==0
      Graphics.update
      Win32API.SetWindowText(_INTL("Processing species {1}...",i))
    end
  end
  dexdata.close
  atkdata.close
  eggEmerald.close
  pokedata.close
  Graphics.update
end



#===============================================================================
# Save Shadow move data to PBS file
#===============================================================================
def pbSaveShadowMoves
  moves = load_data("Data/shadowmoves.dat") rescue []
  File.open("PBS/shadowmoves.txt","wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    f.write("\# "+_INTL("See the documentation on the wiki to learn how to edit this file."))
    f.write("\r\n")
    f.write("\#-------------------------------\r\n")
    for i in 0...moves.length
      move = moves[i]
      if move && moves.length>0
        constname = (getConstantName(PBSpecies,i) rescue pbGetSpeciesConst(i) rescue nil)
        next if !constname
        f.write(sprintf("%s=",constname))
        movenames = []
        for m in move
          movenames.push((getConstantName(PBMoves,m) rescue pbGetMoveConst(m) rescue nil))
        end
        f.write(sprintf("%s\r\n",movenames.compact.join(",")))
      end
    end
  }
end



#===============================================================================
# Save Battle Tower trainer data to PBS file
#===============================================================================
def pbSaveBTTrainers(bttrainers,filename)
  return if !bttrainers || !filename
  btTrainersRequiredTypes = {
     "Type"          => [0,"e",nil],  # Specifies a trainer
     "Name"          => [1,"s"],
     "BeginSpeech"   => [2,"s"],
     "EndSpeechWin"  => [3,"s"],
     "EndSpeechLose" => [4,"s"],
     "PokemonNos"    => [5,"*u"]
  }
  File.open(filename,"wb"){|f|
    f.write(0xEF.chr)
    f.write(0xBB.chr)
    f.write(0xBF.chr)
    for i in 0...bttrainers.length
      next if !bttrainers[i]
      f.write(sprintf("[%03d]\r\n",i))
      for key in btTrainersRequiredTypes.keys
        schema = btTrainersRequiredTypes[key]
        record = bttrainers[i][schema[0]]
        next if record==nil
        f.write(sprintf("%s=",key))
        if key=="Type"
          f.write((getConstantName(PBTrainers,record) rescue pbGetTrainerConst(record)))
        elsif key=="PokemonNos"
          f.write(record.join(",")) # pbWriteCsvRecord somehow won't work here
        else
          pbWriteCsvRecord(record,f,schema)
        end
        f.write(sprintf("\r\n"))
      end
    end
  }
end



#===============================================================================
# Save Battle Tower Pokémon data to PBS file
#===============================================================================
def pbSaveBattlePokemon(btpokemon,filename)
  return if !btpokemon || !filename
  species = {0=>""}
  moves   = {0=>""}
  items   = {0=>""}
  natures = {}
  File.open(filename,"wb"){|f|
    for i in 0...btpokemon.length
      Graphics.update if i%500==0
      pkmn = btpokemon[i]
      f.write(pbFastInspect(pkmn,moves,species,items,natures))
      f.write("\r\n")
    end
  }
end

def pbFastInspect(pkmn,moves,species,items,natures)
  c1 = (species[pkmn.species]) ? species[pkmn.species] :
     (species[pkmn.species] = (getConstantName(PBSpecies,pkmn.species) rescue pbGetSpeciesConst(pkmn.species)))
  c2 = (items[pkmn.item]) ? items[pkmn.item] :
     (items[pkmn.item] = (getConstantName(PBItems,pkmn.item) rescue pbGetItemConst(pkmn.item)))
  c3 = (natures[pkmn.nature]) ? natures[pkmn.nature] :
     (natures[pkmn.nature] = getConstantName(PBNatures,pkmn.nature))
  evlist = ""
  ev = pkmn.ev
  evs = ["HP","ATK","DEF","SPD","SA","SD"]
  for i in 0...ev
    if ((ev&(1<<i))!=0)
      evlist += "," if evlist.length>0
      evlist += evs[i]
    end
  end
  c4 = (moves[pkmn.move1]) ? moves[pkmn.move1] :
     (moves[pkmn.move1] = (getConstantName(PBMoves,pkmn.move1) rescue pbGetMoveConst(pkmn.move1)))
  c5 = (moves[pkmn.move2]) ? moves[pkmn.move2] :
     (moves[pkmn.move2] = (getConstantName(PBMoves,pkmn.move2) rescue pbGetMoveConst(pkmn.move2)))
  c6 = (moves[pkmn.move3]) ? moves[pkmn.move3] :
     (moves[pkmn.move3] = (getConstantName(PBMoves,pkmn.move3) rescue pbGetMoveConst(pkmn.move3)))
  c7 = (moves[pkmn.move4]) ? moves[pkmn.move4] :
     (moves[pkmn.move4] = (getConstantName(PBMoves,pkmn.move4) rescue pbGetMoveConst(pkmn.move4)))
  return "#{c1};#{c2};#{c3};#{evlist};#{c4},#{c5},#{c6},#{c7}"
end



#===============================================================================
# Save all data to PBS files
#===============================================================================
def pbSaveAllData
  pbSaveTypes; Graphics.update
  pbSaveAbilities; Graphics.update
  pbSaveMoveData; Graphics.update
  pbSaveConnectionData; Graphics.update
  pbSaveMetadata; Graphics.update
  pbSaveItems; Graphics.update
  pbSaveBerryPlants; Graphics.update
  pbSaveTrainerLists; Graphics.update
  pbSaveMachines; Graphics.update
  pbSaveEncounterData; Graphics.update
  pbSaveTrainerTypes; Graphics.update
  pbSaveTrainerBattles; Graphics.update
  pbSaveTownMap; Graphics.update
  pbSavePhoneData; Graphics.update
  pbSavePokemonData; Graphics.update
  pbSavePokemonFormsData; Graphics.update
  pbSaveShadowMoves; Graphics.update
end