################################################################################
# Mega Evolutions and Primal Reversions are treated as form changes in
# Essentials. The code below is just more of what's in the Pokemon_MultipleForms
# script section, but specifically and only for the Mega Evolution and Primal
# Reversion forms.
################################################################################
class PokeBattle_Pokemon
  def hasMegaForm?
    v=MultipleForms.call("getMegaForm",self)
    return v!=nil
  end

  def isMega?
    v=MultipleForms.call("getMegaForm",self)
    return v!=nil && v==@form
  end

  def makeMega
    v=MultipleForms.call("getMegaForm",self)
    self.form=v if v!=nil
  end

  def makeUnmega
    v=MultipleForms.call("getUnmegaForm",self)
    self.form=v if v!=nil
  end

  def megaName
    v=MultipleForms.call("getMegaName",self)
    return (v!=nil) ? v : _INTL("Mega {1}",PBSpecies.getName(self.species))
  end

  def megaMessage
    v=MultipleForms.call("megaMessage",self)
    return (v!=nil) ? v : 0   # 0=default message, 1=Rayquaza message
  end

  def hasPrimalForm?
    v=MultipleForms.call("getPrimalForm",self)
    return v!=nil
  end

  def isPrimal?
    v=MultipleForms.call("getPrimalForm",self)
    return v!=nil && v==@form
  end

  def makePrimal
    v=MultipleForms.call("getPrimalForm",self)
    self.form=v if v!=nil
  end

  def makeUnprimal
    v=MultipleForms.call("getUnprimalForm",self)
    self.form=v if v!=nil
  end
end



# XY Mega Evolution ############################################################

MultipleForms.register(:VENUSAUR,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:VENUSAURITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,100,123,80,122,120] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:THICKFAT),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 24 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1555 if pokemon.form==1
   next
}
})

MultipleForms.register(:CHARIZARD,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:CHARIZARDITEX)
   next 2 if isConst?(pokemon.item,PBItems,:CHARIZARDITEY)
   next
},
"getMegaName"=>proc{|pokemon|
   next _INTL("Mega Charizard X") if pokemon.form==1
   next _INTL("Mega Charizard Y") if pokemon.form==2
   next
},
"getBaseStats"=>proc{|pokemon|
   next [78,130,111,100,130,85] if pokemon.form==1
   next [78,104,78,100,159,115] if pokemon.form==2
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:DRAGON) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:TOUGHCLAWS),0]] if pokemon.form==1
   next [[getID(PBAbilities,:DROUGHT),0]] if pokemon.form==2
   next
},
"weight"=>proc{|pokemon|
   next 1105 if pokemon.form==1
   next 1005 if pokemon.form==2
   next
}
})

MultipleForms.register(:BLASTOISE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:BLASTOISINITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [79,103,120,78,135,115] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:MEGALAUNCHER),0]] if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1011 if pokemon.form==1
   next
}
})

MultipleForms.register(:ALAKAZAM,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:ALAKAZITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [55,50,65,150,175,95] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:TRACE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 12 if pokemon.form==1
   next
}
})

MultipleForms.register(:GENGAR,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:GENGARITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [60,65,80,130,170,95] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SHADOWTAG),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 14 if pokemon.form==1
   next
}
})

MultipleForms.register(:KANGASKHAN,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:KANGASKHANITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [105,125,100,100,60,100] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:PARENTALBOND),0]] if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1000 if pokemon.form==1
   next
}
})

MultipleForms.register(:PINSIR,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:PINSIRITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [65,155,120,105,65,90] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:FLYING) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:AERILATE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 17 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 590 if pokemon.form==1
   next
}
})

MultipleForms.register(:GYARADOS,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:GYARADOSITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [95,155,109,81,70,130] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:DARK) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:MOLDBREAKER),0]] if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 3050 if pokemon.form==1
   next
}
})

MultipleForms.register(:AERODACTYL,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:AERODACTYLITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,135,85,150,70,95] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:TOUGHCLAWS),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 21 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 790 if pokemon.form==1
   next
}
})

MultipleForms.register(:MEWTWO,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:MEWTWONITEX)
   next 2 if isConst?(pokemon.item,PBItems,:MEWTWONITEY)
   next
},
"getMegaName"=>proc{|pokemon|
   next _INTL("Mega Mewtwo X") if pokemon.form==1
   next _INTL("Mega Mewtwo Y") if pokemon.form==2
   next
},
"getBaseStats"=>proc{|pokemon|
   next [106,190,100,130,154,100] if pokemon.form==1
   next [106,150,70,140,194,120] if pokemon.form==2
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:FIGHTING) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:STEADFAST),0]] if pokemon.form==1
   next [[getID(PBAbilities,:INSOMNIA),0]] if pokemon.form==2
   next
},
"height"=>proc{|pokemon|
   next 23 if pokemon.form==1
   next 15 if pokemon.form==2
   next
},
"weight"=>proc{|pokemon|
   next 1270 if pokemon.form==1
   next 330 if pokemon.form==2
   next
}
})

MultipleForms.register(:AMPHAROS,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:AMPHAROSITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [90,95,105,45,165,110] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:DRAGON) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:MOLDBREAKER),0]] if pokemon.form==1
   next
}
})

MultipleForms.register(:SCIZOR,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SCIZORITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [70,150,140,75,65,100] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:TECHNICIAN),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 20 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1250 if pokemon.form==1
   next
}
})

MultipleForms.register(:HERACROSS,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:HERACRONITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,185,115,75,40,105] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SKILLLINK),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 17 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 625 if pokemon.form==1
   next
}
})

MultipleForms.register(:HOUNDOOM,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:HOUNDOOMINITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [75,90,90,115,140,90] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SOLARPOWER),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 19 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 495 if pokemon.form==1
   next
}
})

MultipleForms.register(:TYRANITAR,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:TYRANITARITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [100,164,150,71,95,120] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SANDSTREAM),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 25 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 2550 if pokemon.form==1
   next
}
})

MultipleForms.register(:BLAZIKEN,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:BLAZIKENITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,160,80,100,130,80] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SPEEDBOOST),0]] if pokemon.form==1
   next
}
})

MultipleForms.register(:GARDEVOIR,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:GARDEVOIRITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [68,85,65,100,165,135] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:PIXILATE),0]] if pokemon.form==1
   next
}
})

MultipleForms.register(:MAWILE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:MAWILITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [50,105,125,50,55,95] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:HUGEPOWER),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 10 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 235 if pokemon.form==1
   next
}
})

MultipleForms.register(:AGGRON,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:AGGRONITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [70,140,230,50,60,80] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:STEEL) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:FILTER),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 22 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 3950 if pokemon.form==1
   next
}
})

MultipleForms.register(:MEDICHAM,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:MEDICHAMITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [60,100,85,100,80,85] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:PUREPOWER),0]] if pokemon.form==1
   next
}
})

MultipleForms.register(:MANECTRIC,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:MANECTITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [70,75,80,135,135,80] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:INTIMIDATE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 18 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 440 if pokemon.form==1
   next
}
})

MultipleForms.register(:BANETTE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:BANETTTITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [64,165,75,75,93,83] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:PRANKSTER),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 12 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 130 if pokemon.form==1
   next
}
})

MultipleForms.register(:ABSOL,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:ABSOLITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [65,150,60,115,115,60] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:MAGICBOUNCE),0]] if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 490 if pokemon.form==1
   next
}
})

MultipleForms.register(:GARCHOMP,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:GARCHOMPITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [108,170,115,92,120,95] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SANDFORCE),0]] if pokemon.form==1
   next
}
})

MultipleForms.register(:LUCARIO,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:LUCARIONITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [70,145,88,112,140,70] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:ADAPTABILITY),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 13 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 575 if pokemon.form==1
   next
}
})

MultipleForms.register(:ABOMASNOW,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:ABOMASITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [90,132,105,30,132,105] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SNOWWARNING),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 27 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1850 if pokemon.form==1
   next
}
})

# ORAS Mega Evolution ##########################################################

MultipleForms.register(:BEEDRILL,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:BEEDRILLITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [65,150,40,145,15,80] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:ADAPTABILITY),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 14 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 405 if pokemon.form==1
   next
}
})

MultipleForms.register(:PIDGEOT,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:PIDGEOTITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [83,80,80,121,135,80] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:NOGUARD),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 22 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 505 if pokemon.form==1
   next
}
})

MultipleForms.register(:SLOWBRO,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SLOWBRONITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [95,75,180,30,130,80] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SHELLARMOR),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 20 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1200 if pokemon.form==1
   next
}
})

MultipleForms.register(:STEELIX,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:STEELIXITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [75,125,230,30,55,95] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SANDFORCE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 105 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 7400 if pokemon.form==1
   next
}
})

MultipleForms.register(:SCEPTILE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SCEPTILITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [70,110,75,145,145,85] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:DRAGON) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:LIGHTNINGROD),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 19 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 552 if pokemon.form==1
   next
}
})

MultipleForms.register(:SWAMPERT,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SWAMPERTITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [100,150,110,70,95,110] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SWIFTSWIM),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 19 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1020 if pokemon.form==1
   next
}
})

MultipleForms.register(:SABLEYE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SABLENITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [50,85,125,20,85,115] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:MAGICBOUNCE),0]] if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1610 if pokemon.form==1
   next
}
})

MultipleForms.register(:SHARPEDO,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SHARPEDONITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [70,140,70,105,110,65] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:STRONGJAW),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 25 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1303 if pokemon.form==1
   next
}
})

MultipleForms.register(:CAMERUPT,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:CAMERUPTITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [70,120,100,20,145,105] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SHEERFORCE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 25 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 3205 if pokemon.form==1
   next
}
})

MultipleForms.register(:ALTARIA,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:ALTARIANITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [75,110,110,80,110,105] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:FAIRY) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:PIXILATE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 15 if pokemon.form==1
   next
}
})

MultipleForms.register(:GLALIE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:GLALITITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,120,80,100,120,80] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:REFRIGERATE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 21 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 3502 if pokemon.form==1
   next
}
})

MultipleForms.register(:SALAMENCE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SALAMENCITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [95,145,130,120,120,90] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:AERILATE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 18 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 1126 if pokemon.form==1
   next
}
})

MultipleForms.register(:METAGROSS,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:METAGROSSITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,145,150,110,105,110] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:TOUGHCLAWS),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 25 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 9429 if pokemon.form==1
   next
}
})

MultipleForms.register(:LATIAS,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:LATIASITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,100,120,110,140,150] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 18 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 520 if pokemon.form==1
   next
}
})

MultipleForms.register(:LATIOS,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:LATIOSITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [80,130,100,110,160,120] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 23 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 700 if pokemon.form==1
   next
}
})

MultipleForms.register(:RAYQUAZA,{
"getMegaForm"=>proc{|pokemon|
   next 1 if pokemon.hasMove?(:DRAGONASCENT)
   next
},
"megaMessage"=>proc{|pokemon|
   next 1
},
"getBaseStats"=>proc{|pokemon|
   next [105,180,100,115,180,100] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:DELTASTREAM),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 108 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 3920 if pokemon.form==1
   next
}
})

MultipleForms.register(:LOPUNNY,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:LOPUNNITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [65,136,94,135,54,96] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:FIGHTING) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:SCRAPPY),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 13 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 283 if pokemon.form==1
   next
}
})

MultipleForms.register(:GALLADE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:GALLADITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [68,165,95,110,65,115] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:INNERFOCUS),0]] if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 564 if pokemon.form==1
   next
}
})

MultipleForms.register(:AUDINO,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:AUDINITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [103,60,126,50,80,126] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:FAIRY) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:HEALER),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 15 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 320 if pokemon.form==1
   next
}
})

MultipleForms.register(:DIANCIE,{
"getMegaForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:DIANCITE)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [50,160,110,110,160,110] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:MAGICBOUNCE),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 11 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 278 if pokemon.form==1
   next
}
})

# Primal Reversion #############################################################

MultipleForms.register(:KYOGRE,{
"getPrimalForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:BLUEORB)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [100,150,90,90,180,160] if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:PRIMORDIALSEA),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 98 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 4300 if pokemon.form==1
   next
}
})

MultipleForms.register(:GROUDON,{
"getPrimalForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:REDORB)
   next
},
"getBaseStats"=>proc{|pokemon|
   next [100,180,160,90,150,90] if pokemon.form==1
   next
},
"type2"=>proc{|pokemon|
   next getID(PBTypes,:FIRE) if pokemon.form==1
   next
},
"getAbilityList"=>proc{|pokemon|
   next [[getID(PBAbilities,:DESOLATELAND),0]] if pokemon.form==1
   next
},
"height"=>proc{|pokemon|
   next 50 if pokemon.form==1
   next
},
"weight"=>proc{|pokemon|
   next 9997 if pokemon.form==1
   next
}
})
