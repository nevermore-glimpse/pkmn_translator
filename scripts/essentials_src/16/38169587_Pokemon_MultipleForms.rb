class PokeBattle_Pokemon
  attr_accessor(:formTime)   # Time when Furfrou's/Hoopa's form was set

  def form
    return @forcedform if @forcedform!=nil
    v=MultipleForms.call("getForm",self)
    if v!=nil
      self.form=v if !@form || v!=@form
      return v
    end
    return @form || 0
  end

  def form=(value)
    @form=value
    MultipleForms.call("onSetForm",self,value)
    self.calcStats
    pbSeenForm(self)
  end

  def formNoCall=(value)
    @form=value
    self.calcStats
  end

  def forceForm(value)   # Used by the Pokédex only
    @forcedform=value
  end

  alias __mf_baseStats baseStats
  alias __mf_ability ability
  alias __mf_getAbilityList getAbilityList
  alias __mf_type1 type1
  alias __mf_type2 type2
  alias __mf_height height
  alias __mf_weight weight
  alias __mf_getMoveList getMoveList
  alias __mf_isCompatibleWithMove? isCompatibleWithMove?
  alias __mf_wildHoldItems wildHoldItems
  alias __mf_baseExp baseExp
  alias __mf_evYield evYield
  alias __mf_kind kind
  alias __mf_dexEntry dexEntry
  alias __mf_initialize initialize

  def baseStats
    v=MultipleForms.call("getBaseStats",self)
    return v if v!=nil
    return self.__mf_baseStats
  end

  def ability   # DEPRECATED - do not use
    v=MultipleForms.call("ability",self)
    return v if v!=nil
    return self.__mf_ability
  end

  def getAbilityList
    v=MultipleForms.call("getAbilityList",self)
    return v if v!=nil && v.length>0
    return self.__mf_getAbilityList
  end

  def type1
    v=MultipleForms.call("type1",self)
    return v if v!=nil
    return self.__mf_type1
  end

  def type2
    v=MultipleForms.call("type2",self)
    return v if v!=nil
    return self.__mf_type2
  end

  def height
    v=MultipleForms.call("height",self)
    return v if v!=nil
    return self.__mf_height
  end

  def weight
    v=MultipleForms.call("weight",self)
    return v if v!=nil
    return self.__mf_weight
  end

  def getMoveList
    v=MultipleForms.call("getMoveList",self)
    return v if v!=nil
    return self.__mf_getMoveList
  end

  def isCompatibleWithMove?(move)
    v=MultipleForms.call("getMoveCompatibility",self)
    if v!=nil
      return v.any? {|j| j==move }
    end
    return self.__mf_isCompatibleWithMove?(move)
  end

  def wildHoldItems
    v=MultipleForms.call("wildHoldItems",self)
    return v if v!=nil
    return self.__mf_wildHoldItems
  end

  def baseExp
    v=MultipleForms.call("baseExp",self)
    return v if v!=nil
    return self.__mf_baseExp
  end

  def evYield
    v=MultipleForms.call("evYield",self)
    return v if v!=nil
    return self.__mf_evYield
  end

  def kind
    v=MultipleForms.call("kind",self)
    return v if v!=nil
    return self.__mf_kind
  end

  def dexEntry
    v=MultipleForms.call("dexEntry",self)
    return v if v!=nil
    return self.__mf_dexEntry
  end

  def initialize(*args)
    __mf_initialize(*args)
    f=MultipleForms.call("getFormOnCreation",self)
    if f
      self.form=f
      self.resetMoves
    end
  end
end



class PokeBattle_RealBattlePeer
  def pbOnEnteringBattle(battle,pokemon)
    f=MultipleForms.call("getFormOnEnteringBattle",pokemon)
    if f
      pokemon.form=f
    end
  end
end



module MultipleForms
  @@formSpecies=HandlerHash.new(:PBSpecies)

  def self.copy(sym,*syms)
    @@formSpecies.copy(sym,*syms)
  end

  def self.register(sym,hash)
    @@formSpecies.add(sym,hash)
  end

  def self.registerIf(cond,hash)
    @@formSpecies.addIf(cond,hash)
  end

  def self.hasFunction?(pokemon,func)
    spec=(pokemon.is_a?(Numeric)) ? pokemon : pokemon.species
    sp=@@formSpecies[spec]
    return sp && sp[func]
  end

  def self.getFunction(pokemon,func)
    spec=(pokemon.is_a?(Numeric)) ? pokemon : pokemon.species
    sp=@@formSpecies[spec]
    return (sp && sp[func]) ? sp[func] : nil
  end

  def self.call(func,pokemon,*args)
    sp=@@formSpecies[pokemon.species]
    return nil if !sp || !sp[func]
    return sp[func].call(pokemon,*args)
  end
end



def drawSpot(bitmap,spotpattern,x,y,red,green,blue)
  height=spotpattern.length
  width=spotpattern[0].length
  for yy in 0...height
    spot=spotpattern[yy]
    for xx in 0...width
      if spot[xx]==1
        xOrg=(x+xx)<<1
        yOrg=(y+yy)<<1
        color=bitmap.get_pixel(xOrg,yOrg)
        r=color.red+red
        g=color.green+green
        b=color.blue+blue
        color.red=[[r,0].max,255].min
        color.green=[[g,0].max,255].min
        color.blue=[[b,0].max,255].min
        bitmap.set_pixel(xOrg,yOrg,color)
        bitmap.set_pixel(xOrg+1,yOrg,color)
        bitmap.set_pixel(xOrg,yOrg+1,color)
        bitmap.set_pixel(xOrg+1,yOrg+1,color)
      end   
    end
  end
end

def pbSpindaSpots(pokemon,bitmap)
  spot1=[
     [0,0,1,1,1,1,0,0],
     [0,1,1,1,1,1,1,0],
     [1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1],
     [0,1,1,1,1,1,1,0],
     [0,0,1,1,1,1,0,0]
  ]
  spot2=[
     [0,0,1,1,1,0,0],
     [0,1,1,1,1,1,0],
     [1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1],
     [0,1,1,1,1,1,0],
     [0,0,1,1,1,0,0]
  ]
  spot3=[
     [0,0,0,0,0,1,1,1,1,0,0,0,0],
     [0,0,0,1,1,1,1,1,1,1,0,0,0],
     [0,0,1,1,1,1,1,1,1,1,1,0,0],
     [0,1,1,1,1,1,1,1,1,1,1,1,0],
     [0,1,1,1,1,1,1,1,1,1,1,1,0],
     [1,1,1,1,1,1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1,1,1,1,1,1],
     [0,1,1,1,1,1,1,1,1,1,1,1,0],
     [0,1,1,1,1,1,1,1,1,1,1,1,0],
     [0,0,1,1,1,1,1,1,1,1,1,0,0],
     [0,0,0,1,1,1,1,1,1,1,0,0,0],
     [0,0,0,0,0,1,1,1,0,0,0,0,0]
  ]
  spot4=[
     [0,0,0,0,1,1,1,0,0,0,0,0],
     [0,0,1,1,1,1,1,1,1,0,0,0],
     [0,1,1,1,1,1,1,1,1,1,0,0],
     [0,1,1,1,1,1,1,1,1,1,1,0],
     [1,1,1,1,1,1,1,1,1,1,1,0],
     [1,1,1,1,1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1,1,1,1,1],
     [1,1,1,1,1,1,1,1,1,1,1,0],
     [0,1,1,1,1,1,1,1,1,1,1,0],
     [0,0,1,1,1,1,1,1,1,1,0,0],
     [0,0,0,0,1,1,1,1,1,0,0,0]
  ]
  id=pokemon.personalID
  h=(id>>28)&15
  g=(id>>24)&15
  f=(id>>20)&15
  e=(id>>16)&15
  d=(id>>12)&15
  c=(id>>8)&15
  b=(id>>4)&15
  a=(id)&15
  if pokemon.isShiny?
    drawSpot(bitmap,spot1,b+33,a+25,-75,-10,-150)
    drawSpot(bitmap,spot2,d+21,c+24,-75,-10,-150)
    drawSpot(bitmap,spot3,f+39,e+7,-75,-10,-150)
    drawSpot(bitmap,spot4,h+15,g+6,-75,-10,-150)
  else
    drawSpot(bitmap,spot1,b+33,a+25,0,-115,-75)
    drawSpot(bitmap,spot2,d+21,c+24,0,-115,-75)
    drawSpot(bitmap,spot3,f+39,e+7,0,-115,-75)
    drawSpot(bitmap,spot4,h+15,g+6,0,-115,-75)
  end
end

################################################################################

MultipleForms.register(:UNOWN,{
"getFormOnCreation"=>proc{|pokemon|
   next rand(28)
}
})

MultipleForms.register(:SPINDA,{
"alterBitmap"=>proc{|pokemon,bitmap|
   pbSpindaSpots(pokemon,bitmap)
}
})

MultipleForms.register(:CASTFORM,{
"type1"=>proc{|pokemon|
   next if pokemon.form==0            # Normal Form
   case pokemon.form
   when 1; next getID(PBTypes,:FIRE)  # Sunny Form
   when 2; next getID(PBTypes,:WATER) # Rainy Form
   when 3; next getID(PBTypes,:ICE)   # Snowy Form
   end
},
"type2"=>proc{|pokemon|
   next if pokemon.form==0            # Normal Form
   case pokemon.form
   when 1; next getID(PBTypes,:FIRE)  # Sunny Form
   when 2; next getID(PBTypes,:WATER) # Rainy Form
   when 3; next getID(PBTypes,:ICE)   # Snowy Form
   end
}
})

MultipleForms.register(:DEOXYS,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0               # Normal Forme
   case pokemon.form
   when 1; next [50,180, 20,150,180, 20] # Attack Forme
   when 2; next [50, 70,160, 90, 70,160] # Defense Forme
   when 3; next [50, 95, 90,180, 95, 90] # Speed Forme
   end
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0    # Normal Forme
   case pokemon.form
   when 1; next [0,2,0,0,1,0] # Attack Forme
   when 2; next [0,0,2,0,0,1] # Defense Forme
   when 3; next [0,0,0,3,0,0] # Speed Forme
   end
},
"getMoveList"=>proc{|pokemon|
   next if pokemon.form==0
   movelist=[]
   case pokemon.form
   when 1; movelist=[[1,:LEER],[1,:WRAP],[9,:NIGHTSHADE],[17,:TELEPORT],
                     [25,:TAUNT],[33,:PURSUIT],[41,:PSYCHIC],[49,:SUPERPOWER],
                     [57,:PSYCHOSHIFT],[65,:ZENHEADBUTT],[73,:COSMICPOWER],
                     [81,:ZAPCANNON],[89,:PSYCHOBOOST],[97,:HYPERBEAM]]
   when 2; movelist=[[1,:LEER],[1,:WRAP],[9,:NIGHTSHADE],[17,:TELEPORT],
                     [25,:KNOCKOFF],[33,:SPIKES],[41,:PSYCHIC],[49,:SNATCH],
                     [57,:PSYCHOSHIFT],[65,:ZENHEADBUTT],[73,:IRONDEFENSE],
                     [73,:AMNESIA],[81,:RECOVER],[89,:PSYCHOBOOST],
                     [97,:COUNTER],[97,:MIRRORCOAT]]
   when 3; movelist=[[1,:LEER],[1,:WRAP],[9,:NIGHTSHADE],[17,:DOUBLETEAM],
                     [25,:KNOCKOFF],[33,:PURSUIT],[41,:PSYCHIC],[49,:SWIFT],
                     [57,:PSYCHOSHIFT],[65,:ZENHEADBUTT],[73,:AGILITY],
                     [81,:RECOVER],[89,:PSYCHOBOOST],[97,:EXTREMESPEED]]
   end
   for i in movelist
     i[1]=getConst(PBMoves,i[1])
   end
   next movelist
}
})

MultipleForms.register(:BURMY,{
"getFormOnCreation"=>proc{|pokemon|
   env=pbGetEnvironment()
   if !pbGetMetadata($game_map.map_id,MetadataOutdoor)
     next 2 # Trash Cloak
   elsif env==PBEnvironment::Sand ||
         env==PBEnvironment::Rock ||
         env==PBEnvironment::Cave
     next 1 # Sandy Cloak
   else
     next 0 # Plant Cloak
   end
},
"getFormOnEnteringBattle"=>proc{|pokemon|
   env=pbGetEnvironment()
   if !pbGetMetadata($game_map.map_id,MetadataOutdoor)
     next 2 # Trash Cloak
   elsif env==PBEnvironment::Sand ||
         env==PBEnvironment::Rock ||
         env==PBEnvironment::Cave
     next 1 # Sandy Cloak
   else
     next 0 # Plant Cloak
   end
}
})

MultipleForms.register(:WORMADAM,{
"getFormOnCreation"=>proc{|pokemon|
   env=pbGetEnvironment()
   if !pbGetMetadata($game_map.map_id,MetadataOutdoor)
     next 2 # Trash Cloak
   elsif env==PBEnvironment::Sand || env==PBEnvironment::Rock ||
      env==PBEnvironment::Cave
     next 1 # Sandy Cloak
   else
     next 0 # Plant Cloak
   end
},
"type2"=>proc{|pokemon|
   next if pokemon.form==0             # Plant Cloak
   case pokemon.form
   when 1; next getID(PBTypes,:GROUND) # Sandy Cloak
   when 2; next getID(PBTypes,:STEEL)  # Trash Cloak
   end
},
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0            # Plant Cloak
   case pokemon.form
   when 1; next [60,79,105,36,59, 85] # Sandy Cloak
   when 2; next [60,69, 95,36,69, 95] # Trash Cloak
   end
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0    # Plant Cloak
   case pokemon.form
   when 1; next [0,0,2,0,0,0] # Sandy Cloak
   when 2; next [0,0,1,0,0,1] # Trash Cloak
   end
},
"getMoveList"=>proc{|pokemon|
   next if pokemon.form==0
   movelist=[]
   case pokemon.form
   when 1; movelist=[[1,:TACKLE],[10,:PROTECT],[15,:BUGBITE],[20,:HIDDENPOWER],
                     [23,:CONFUSION],[26,:ROCKBLAST],[29,:HARDEN],[32,:PSYBEAM],
                     [35,:CAPTIVATE],[38,:FLAIL],[41,:ATTRACT],[44,:PSYCHIC],
                     [47,:FISSURE]]
   when 2; movelist=[[1,:TACKLE],[10,:PROTECT],[15,:BUGBITE],[20,:HIDDENPOWER],
                     [23,:CONFUSION],[26,:MIRRORSHOT],[29,:METALSOUND],
                     [32,:PSYBEAM],[35,:CAPTIVATE],[38,:FLAIL],[41,:ATTRACT],
                     [44,:PSYCHIC],[47,:IRONHEAD]]
   end
   for i in movelist
     i[1]=getConst(PBMoves,i[1])
   end
   next movelist
},
"getMoveCompatibility"=>proc{|pokemon|
   next if pokemon.form==0
   movelist=[]
   case pokemon.form
   when 1; movelist=[# TMs
                     :TOXIC,:VENOSHOCK,:HIDDENPOWER,:SUNNYDAY,:HYPERBEAM,
                     :PROTECT,:RAINDANCE,:SAFEGUARD,:FRUSTRATION,:EARTHQUAKE,
                     :RETURN,:DIG,:PSYCHIC,:SHADOWBALL,:DOUBLETEAM,
                     :SANDSTORM,:ROCKTOMB,:FACADE,:REST,:ATTRACT,
                     :THIEF,:ROUND,:GIGAIMPACT,:FLASH,:STRUGGLEBUG,
                     :PSYCHUP,:BULLDOZE,:DREAMEATER,:SWAGGER,:SUBSTITUTE,
                     # Move Tutors
                     :BUGBITE,:EARTHPOWER,:ELECTROWEB,:ENDEAVOR,:MUDSLAP,
                     :SIGNALBEAM,:SKILLSWAP,:SLEEPTALK,:SNORE,:STEALTHROCK,
                     :STRINGSHOT,:SUCKERPUNCH,:UPROAR]
   when 2; movelist=[# TMs
                     :TOXIC,:VENOSHOCK,:HIDDENPOWER,:SUNNYDAY,:HYPERBEAM,
                     :PROTECT,:RAINDANCE,:SAFEGUARD,:FRUSTRATION,:RETURN,
                     :PSYCHIC,:SHADOWBALL,:DOUBLETEAM,:FACADE,:REST,
                     :ATTRACT,:THIEF,:ROUND,:GIGAIMPACT,:FLASH,
                     :GYROBALL,:STRUGGLEBUG,:PSYCHUP,:DREAMEATER,:SWAGGER,
                     :SUBSTITUTE,:FLASHCANNON,
                     # Move Tutors
                     :BUGBITE,:ELECTROWEB,:ENDEAVOR,:GUNKSHOT,:IRONDEFENSE,
                     :IRONHEAD,:MAGNETRISE,:SIGNALBEAM,:SKILLSWAP,:SLEEPTALK,
                     :SNORE,:STEALTHROCK,:STRINGSHOT,:SUCKERPUNCH,:UPROAR]
   end
   for i in 0...movelist.length
     movelist[i]=getConst(PBMoves,movelist[i])
   end
   next movelist
}
})

MultipleForms.register(:SHELLOS,{
"getFormOnCreation"=>proc{|pokemon|
   maps=[2,5,39,41,44,69]   # Map IDs for second form
   if $game_map && maps.include?($game_map.map_id)
     next 1
   else
     next 0
   end
}
})

MultipleForms.copy(:SHELLOS,:GASTRODON)

MultipleForms.register(:ROTOM,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0     # Normal Form
   next [50,65,107,86,105,107] # All alternate forms
},
"type2"=>proc{|pokemon|
   next if pokemon.form==0             # Normal Form
   case pokemon.form
   when 1; next getID(PBTypes,:FIRE)   # Heat, Microwave
   when 2; next getID(PBTypes,:WATER)  # Wash, Washing Machine
   when 3; next getID(PBTypes,:ICE)    # Frost, Refrigerator
   when 4; next getID(PBTypes,:FLYING) # Fan
   when 5; next getID(PBTypes,:GRASS)  # Mow, Lawnmower
   end
},
"onSetForm"=>proc{|pokemon,form|
   moves=[
      :OVERHEAT,  # Heat, Microwave
      :HYDROPUMP, # Wash, Washing Machine
      :BLIZZARD,  # Frost, Refrigerator
      :AIRSLASH,  # Fan
      :LEAFSTORM  # Mow, Lawnmower
   ]
   hasoldmove=-1
   for i in 0...4
     for j in 0...moves.length
       if isConst?(pokemon.moves[i].id,PBMoves,moves[j])
         hasoldmove=i; break
       end
     end
     break if hasoldmove>=0
   end
   if form>0
     newmove=moves[form-1]
     if newmove!=nil && hasConst?(PBMoves,newmove)
       if hasoldmove>=0
         # Automatically replace the old form's special move with the new one's
         oldmovename=PBMoves.getName(pokemon.moves[hasoldmove].id)
         newmovename=PBMoves.getName(getID(PBMoves,newmove))
         pokemon.moves[hasoldmove]=PBMove.new(getID(PBMoves,newmove))
         Kernel.pbMessage(_INTL("\\se[]1,\\wt[4] 2,\\wt[4] and...\\wt[8] ...\\wt[8] ...\\wt[8] Poof!\\se[balldrop]\1"))
         Kernel.pbMessage(_INTL("{1} forgot how to\r\nuse {2}.\1",pokemon.name,oldmovename))
         Kernel.pbMessage(_INTL("And...\1"))
         Kernel.pbMessage(_INTL("\\se[]{1} learned {2}!\\se[MoveLearnt]",pokemon.name,newmovename))
       else
         # Try to learn the new form's special move
         pbLearnMove(pokemon,getID(PBMoves,newmove),true)
       end
     end
   else
     if hasoldmove>=0
       # Forget the old form's special move
       oldmovename=PBMoves.getName(pokemon.moves[hasoldmove].id)
       pokemon.pbDeleteMoveAtIndex(hasoldmove)
       Kernel.pbMessage(_INTL("{1} forgot {2}...",pokemon.name,oldmovename))
       if pokemon.moves.find_all{|i| i.id!=0}.length==0
         pbLearnMove(pokemon,getID(PBMoves,:THUNDERSHOCK))
       end
     end
   end
}
})

MultipleForms.register(:GIRATINA,{
"getAbilityList"=>proc{|pokemon|
   next if pokemon.form==0                  # Altered Forme
   next [[getID(PBAbilities,:LEVITATE),0],
         [getID(PBAbilities,:TELEPATHY),2]] # Origin Forme
},
"height"=>proc{|pokemon|
   next if pokemon.form==0 # Altered Forme
   next 69                 # Origin Forme
},
"weight"=>proc{|pokemon|
   next if pokemon.form==0 # Altered Forme
   next 6500               # Origin Forme
},
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0       # Altered Forme
   next [150,120,100,90,120,100] # Origin Forme
},
"getForm"=>proc{|pokemon|
   maps=[49,50,51,72,73]   # Map IDs for Origin Forme
   if isConst?(pokemon.item,PBItems,:GRISEOUSORB) ||
      ($game_map && maps.include?($game_map.map_id))
     next 1
   end
   next 0
}
})

MultipleForms.register(:SHAYMIN,{
"type2"=>proc{|pokemon|
   next if pokemon.form==0     # Land Forme
   next getID(PBTypes,:FLYING) # Sky Forme
},
"getAbilityList"=>proc{|pokemon|
   next if pokemon.form==0                    # Land Forme
   next [[getID(PBAbilities,:SERENEGRACE),0]] # Sky Forme
},
"height"=>proc{|pokemon|
   next if pokemon.form==0 # Land Forme
   next 69                 # Sky Forme
},
"weight"=>proc{|pokemon|
   next if pokemon.form==0 # Land Forme
   next 4                  # Sky Forme
},
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0      # Land Forme
   next [100,103,75,127,120,75] # Sky Forme
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0 # Land Forme
   next [0,0,0,3,0,0]      # Sky Forme
},
"getForm"=>proc{|pokemon|
   next 0 if pokemon.hp<=0 || pokemon.status==PBStatuses::FROZEN ||
             PBDayNight.isNight?
   next nil
},
"getMoveList"=>proc{|pokemon|
   next if pokemon.form==0
   movelist=[]
   case pokemon.form
   when 1; movelist=[[1,:GROWTH],[10,:MAGICALLEAF],[19,:LEECHSEED],
                     [28,:QUICKATTACK],[37,:SWEETSCENT],[46,:NATURALGIFT],
                     [55,:WORRYSEED],[64,:AIRSLASH],[73,:ENERGYBALL],
                     [82,:SWEETKISS],[91,:LEAFSTORM],[100,:SEEDFLARE]]
   end
   for i in movelist
     i[1]=getConst(PBMoves,i[1])
   end
   next movelist
}
})

MultipleForms.register(:ARCEUS,{
"type1"=>proc{|pokemon|
   types=[:NORMAL,:FIGHTING,:FLYING,:POISON,:GROUND,
          :ROCK,:BUG,:GHOST,:STEEL,:QMARKS,
          :FIRE,:WATER,:GRASS,:ELECTRIC,:PSYCHIC,
          :ICE,:DRAGON,:DARK,:FAIRY]
   next getID(PBTypes,types[pokemon.form])
},
"type2"=>proc{|pokemon|
   types=[:NORMAL,:FIGHTING,:FLYING,:POISON,:GROUND,
          :ROCK,:BUG,:GHOST,:STEEL,:QMARKS,
          :FIRE,:WATER,:GRASS,:ELECTRIC,:PSYCHIC,
          :ICE,:DRAGON,:DARK,:FAIRY]
   next getID(PBTypes,types[pokemon.form])
},
"getForm"=>proc{|pokemon|
   next 1  if isConst?(pokemon.item,PBItems,:FISTPLATE)
   next 2  if isConst?(pokemon.item,PBItems,:SKYPLATE)
   next 3  if isConst?(pokemon.item,PBItems,:TOXICPLATE)
   next 4  if isConst?(pokemon.item,PBItems,:EARTHPLATE)
   next 5  if isConst?(pokemon.item,PBItems,:STONEPLATE)
   next 6  if isConst?(pokemon.item,PBItems,:INSECTPLATE)
   next 7  if isConst?(pokemon.item,PBItems,:SPOOKYPLATE)
   next 8  if isConst?(pokemon.item,PBItems,:IRONPLATE)
   next 10 if isConst?(pokemon.item,PBItems,:FLAMEPLATE)
   next 11 if isConst?(pokemon.item,PBItems,:SPLASHPLATE)
   next 12 if isConst?(pokemon.item,PBItems,:MEADOWPLATE)
   next 13 if isConst?(pokemon.item,PBItems,:ZAPPLATE)
   next 14 if isConst?(pokemon.item,PBItems,:MINDPLATE)
   next 15 if isConst?(pokemon.item,PBItems,:ICICLEPLATE)
   next 16 if isConst?(pokemon.item,PBItems,:DRACOPLATE)
   next 17 if isConst?(pokemon.item,PBItems,:DREADPLATE)
   next 18 if isConst?(pokemon.item,PBItems,:PIXIEPLATE)
   next 0
}
})

MultipleForms.register(:BASCULIN,{
"getFormOnCreation"=>proc{|pokemon|
   next rand(2)
},
"getAbilityList"=>proc{|pokemon|
   next if pokemon.form==0                    # Red-Striped
   next [[getID(PBAbilities,:ROCKHEAD),0],
         [getID(PBAbilities,:ADAPTABILITY),1],
         [getID(PBAbilities,:MOLDBREAKER),2]] # Blue-Striped
},
"wildHoldItems"=>proc{|pokemon|
   next if pokemon.form==0                 # Red-Striped
   next [0,getID(PBItems,:DEEPSEASCALE),0] # Blue-Striped
}
})

MultipleForms.register(:DARMANITAN,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0      # Standard Mode
   next [105,30,105,55,140,105] # Zen Mode
},
"type2"=>proc{|pokemon|
   next if pokemon.form==0      # Standard Mode
   next getID(PBTypes,:PSYCHIC) # Zen Mode
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0 # Standard Mode
   next [0,0,0,0,2,0]      # Zen Mode
}
})

MultipleForms.register(:DEERLING,{
"getForm"=>proc{|pokemon|
   next pbGetSeason
}
})

MultipleForms.copy(:DEERLING,:SAWSBUCK)

MultipleForms.register(:TORNADUS,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0     # Incarnate Forme
   next [79,100,80,121,110,90] # Therian Forme
},
"height"=>proc{|pokemon|
   next if pokemon.form==0 # Incarnate Forme
   next 14                 # Therian Forme
},
"getAbilityList"=>proc{|pokemon|
   next if pokemon.form==0                    # Incarnate Forme
   next [[getID(PBAbilities,:REGENERATOR),0],
         [getID(PBAbilities,:DEFIANT),2]]     # Therian Forme
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0 # Incarnate Forme
   next [0,0,0,3,0,0]      # Therian Forme
}
})

MultipleForms.register(:THUNDURUS,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0     # Incarnate Forme
   next [79,105,70,101,145,80] # Therian Forme
},
"height"=>proc{|pokemon|
   next if pokemon.form==0 # Incarnate Forme
   next 30                 # Therian Forme
},
"getAbilityList"=>proc{|pokemon|
   next if pokemon.form==0                   # Incarnate Forme
   next [[getID(PBAbilities,:VOLTABSORB),0],
         [getID(PBAbilities,:DEFIANT),2]]    # Therian Forme
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0 # Incarnate Forme
   next [0,0,0,0,3,0]      # Therian Forme
}
})

MultipleForms.register(:LANDORUS,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0    # Incarnate Forme
   next [89,145,90,71,105,80] # Therian Forme
},
"height"=>proc{|pokemon|
   next if pokemon.form==0 # Incarnate Forme
   next 13                 # Therian Forme
},
"getAbilityList"=>proc{|pokemon|
   next if pokemon.form==0                   # Incarnate Forme
   next [[getID(PBAbilities,:INTIMIDATE),0],
         [getID(PBAbilities,:SHEERFORCE),2]] # Therian Forme
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0 # Incarnate Forme
   next [0,3,0,0,0,0]      # Therian Forme
}
})

MultipleForms.register(:KYUREM,{
"getBaseStats"=>proc{|pokemon|
   case pokemon.form
   when 1; next [125,120, 90,95,170,100] # White Kyurem
   when 2; next [125,170,100,95,120, 90] # Black Kyurem
   else;   next                          # Kyurem
   end
},
"height"=>proc{|pokemon|
   case pokemon.form
   when 1; next 36 # White Kyurem
   when 2; next 33 # Black Kyurem
   else;   next    # Kyurem
   end
},
"getAbilityList"=>proc{|pokemon|
   case pokemon.form
   when 1; next [[getID(PBAbilities,:TURBOBLAZE),0]] # White Kyurem
   when 2; next [[getID(PBAbilities,:TERAVOLT),0]]   # Black Kyurem
   else;   next                                      # Kyurem
   end
},
"evYield"=>proc{|pokemon|
   case pokemon.form
   when 1; next [0,0,0,0,3,0] # White Kyurem
   when 2; next [0,3,0,0,0,0] # Black Kyurem
   else;   next               # Kyurem
   end
},
"getMoveList"=>proc{|pokemon|
   next if pokemon.form==0
   movelist=[]
   case pokemon.form
   when 1; movelist=[[1,:ICYWIND],[1,:DRAGONRAGE],[8,:IMPRISON],
                     [15,:ANCIENTPOWER],[22,:ICEBEAM],[29,:DRAGONBREATH],
                     [36,:SLASH],[43,:FUSIONFLARE],[50,:ICEBURN],
                     [57,:DRAGONPULSE],[64,:IMPRISON],[71,:ENDEAVOR],
                     [78,:BLIZZARD],[85,:OUTRAGE],[92,:HYPERVOICE]]
   when 2; movelist=[[1,:ICYWIND],[1,:DRAGONRAGE],[8,:IMPRISON],
                     [15,:ANCIENTPOWER],[22,:ICEBEAM],[29,:DRAGONBREATH],
                     [36,:SLASH],[43,:FUSIONBOLT],[50,:FREEZESHOCK],
                     [57,:DRAGONPULSE],[64,:IMPRISON],[71,:ENDEAVOR],
                     [78,:BLIZZARD],[85,:OUTRAGE],[92,:HYPERVOICE]]
   end
   for i in movelist
     i[1]=getConst(PBMoves,i[1])
   end
   next movelist
}
})

MultipleForms.register(:KELDEO,{
"getForm"=>proc{|pokemon|
   next 1 if pokemon.hasMove?(:SECRETSWORD) # Resolute Form
   next 0                                   # Ordinary Form
}
})

MultipleForms.register(:MELOETTA,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0     # Aria Forme
   next [100,128,90,128,77,77] # Pirouette Forme
},
"type2"=>proc{|pokemon|
   next if pokemon.form==0       # Aria Forme
   next getID(PBTypes,:FIGHTING) # Pirouette Forme
},
"evYield"=>proc{|pokemon|
   next if pokemon.form==0 # Aria Forme
   next [0,1,1,1,0,0]      # Pirouette Forme
}
})

MultipleForms.register(:GENESECT,{
"getForm"=>proc{|pokemon|
   next 1 if isConst?(pokemon.item,PBItems,:SHOCKDRIVE)
   next 2 if isConst?(pokemon.item,PBItems,:BURNDRIVE)
   next 3 if isConst?(pokemon.item,PBItems,:CHILLDRIVE)
   next 4 if isConst?(pokemon.item,PBItems,:DOUSEDRIVE)
   next 0
}
})

MultipleForms.register(:SCATTERBUG,{
"getFormOnCreation"=>proc{|pokemon|
   next $Trainer.secretID%18
},
})

MultipleForms.copy(:SCATTERBUG,:SPEWPA,:VIVILLON)

MultipleForms.register(:FLABEBE,{
"getFormOnCreation"=>proc{|pokemon|
   next rand(5)
},
})

MultipleForms.copy(:FLABEBE,:FLOETTE,:FLORGES)

MultipleForms.register(:FURFROU,{
"getForm"=>proc{|pokemon|
   if !pokemon.formTime || pbGetTimeNow.to_i>pokemon.formTime.to_i+60*60*24*5 # 5 days
     next 0
   end
   next
},
"onSetForm"=>proc{|pokemon,form|
   pokemon.formTime=(form>0) ? pbGetTimeNow.to_i : nil
}
})

MultipleForms.register(:MEOWSTIC,{
"getAbilityList"=>proc{|pokemon|
   next if pokemon.isMale?
   next [[getID(PBAbilities,:KEENEYE),0],
         [getID(PBAbilities,:INFILTRATOR),1],
         [getID(PBAbilities,:COMPETITIVE),2]]
},
"getMoveList"=>proc{|pokemon|
   if pokemon.isFemale?
     movelist=[[1,:STOREDPOWER],[1,:MEFIRST],[1,:MAGICALLEAF],[1,:SCRATCH],
               [1,:LEER],[5,:COVET],[9,:CONFUSION],[13,:LIGHTSCREEN],
               [17,:PSYBEAM],[19,:FAKEOUT],[22,:DISARMINGVOICE],[25,:PSYSHOCK],
               [28,:CHARGEBEAM],[31,:SHADOWBALL],[35,:EXTRASENSORY],
               [40,:PSYCHIC],[43,:ROLEPLAY],[45,:SIGNALBEAM],[48,:SUCKERPUNCH],
               [50,:FUTURESIGHT],[53,:STOREDPOWER]]
     for i in movelist
       i[1]=getConst(PBMoves,i[1])
     end
     next movelist
   end
   next
}
})

MultipleForms.register(:AEGISLASH,{
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0      # Shield Forme
   next [60,150,50,60,150,50]   # Blade Forme
}
})

MultipleForms.register(:PUMPKABOO,{
"getFormOnCreation"=>proc{|pokemon|
   next [rand(4),rand(4)].min
},
"height"=>proc{|pokemon|
   next if pokemon.form==0     # Small Size
   next 4 if pokemon.form==1   # Average Size
   next 5 if pokemon.form==2   # Large Size
   next 8 if pokemon.form==3   # Super Size
},
"weight"=>proc{|pokemon|
   next if pokemon.form==0       # Small Size
   next 50 if pokemon.form==1    # Average Size
   next 75 if pokemon.form==2    # Large Size
   next 150 if pokemon.form==3   # Super Size
},
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0                       # Small Size
   next [49,66,70,51,44,55] if pokemon.form==1   # Average Size
   next [54,66,70,46,44,55] if pokemon.form==2   # Large Size
   next [59,66,70,41,44,55] if pokemon.form==3   # Super Size
},
"wildHoldItems"=>proc{|pokemon|
   next [getID(PBItems,:MIRACLESEED),
         getID(PBItems,:MIRACLESEED),
         getID(PBItems,:MIRACLESEED)] if pokemon.form==3 # Super Size
   next
}
})

MultipleForms.register(:GOURGEIST,{
"getFormOnCreation"=>proc{|pokemon|
   next [rand(4),rand(4)].min
},
"height"=>proc{|pokemon|
   next if pokemon.form==0      # Small Size
   next 9 if pokemon.form==1    # Average Size
   next 11 if pokemon.form==2   # Large Size
   next 17 if pokemon.form==3   # Super Size
},
"weight"=>proc{|pokemon|
   next if pokemon.form==0       # Small Size
   next 125 if pokemon.form==1   # Average Size
   next 140 if pokemon.form==2   # Large Size
   next 390 if pokemon.form==3   # Super Size
},
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0                         # Small Size
   next [65,90,122,84,58,75] if pokemon.form==1    # Average Size
   next [75,95,122,69,58,75] if pokemon.form==2    # Large Size
   next [85,100,122,54,58,75] if pokemon.form==3   # Super Size
}
})

MultipleForms.register(:XERNEAS,{
"getFormOnEnteringBattle"=>proc{|pokemon|
   next 1
}
})

MultipleForms.register(:HOOPA,{
"getForm"=>proc{|pokemon|
   if !pokemon.formTime || pbGetTimeNow.to_i>pokemon.formTime.to_i+60*60*24*3 # 3 days
     next 0
   end
   next
},
"type2"=>proc{|pokemon|
   next if pokemon.form==0     # Confined
   next getID(PBTypes,:DARK)   # Unbound
},
"getBaseStats"=>proc{|pokemon|
   next if pokemon.form==0       # Confined
   next [80,160,60,80,170,130]   # Unbound
},
"height"=>proc{|pokemon|
   next if pokemon.form==0   # Confined
   next 65                   # Unbound
},
"weight"=>proc{|pokemon|
   next if pokemon.form==0   # Confined
   next 4900                 # Unbound
},
"getMoveList"=>proc{|pokemon|
   next if pokemon.form==0
   movelist=[[1,:HYPERSPACEFURY],[1,:TRICK],[1,:DESTINYBOND],[1,:ALLYSWITCH],
             [1,:CONFUSION],[6,:ASTONISH],[10,:MAGICCOAT],[15,:LIGHTSCREEN],
             [19,:PSYBEAM],[25,:SKILLSWAP],[29,:POWERSPLIT],[29,:GUARDSPLIT],
             [46,:KNOCKOFF],[50,:WONDERROOM],[50,:TRICKROOM],[55,:DARKPULSE],
             [75,:PSYCHIC],[85,:HYPERSPACEFURY]]
   for i in movelist
     i[1]=getConst(PBMoves,i[1])
   end
   next movelist
},
"kind"=>proc{|pokemon|
   next if pokemon.form==0   # Confined
   next _INTL("Djinn")       # Unbound
},
"onSetForm"=>proc{|pokemon,form|
   pokemon.formTime=(form>0) ? pbGetTimeNow.to_i : nil
}
})