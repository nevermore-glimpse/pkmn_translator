class PokeBattle_Pokemon
  attr_accessor(:formTime)   # Time when Furfrou's/Hoopa's form was set
  attr_accessor(:forcedForm)

  def form
    return @forcedForm if @forcedForm!=nil
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

  def fSpecies
    return pbGetFSpeciesFromForm(@species,self.form)
  end
  
  alias __mf_isCompatibleWithMove? isCompatibleWithMove? # Not purged from below
  alias __mf_initialize initialize

  def isCompatibleWithMove?(move)
    v=MultipleForms.call("getMoveCompatibility",self)
    if v!=nil
      return v.any? {|j| j==move }
    end
    return self.__mf_isCompatibleWithMove?(move)
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
  @@formSpecies = HandlerHash.new(:PBSpecies)

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
     newmove = moves[form-1]
     if newmove!=nil && hasConst?(PBMoves,newmove)
       if hasoldmove>=0
         # Automatically replace the old form's special move with the new one's
         oldmovename = PBMoves.getName(pokemon.moves[hasoldmove].id)
         newmovename = PBMoves.getName(getID(PBMoves,newmove))
         pokemon.moves[hasoldmove] = PBMove.new(getID(PBMoves,newmove))
         Kernel.pbMessage(_INTL("1,\\wt[16] 2, and\\wt[16]...\\wt[16] ...\\wt[16] ... Ta-da!\\se[Battle ball drop]\1"))
         Kernel.pbMessage(_INTL("{1} forgot how to use {2}.\\nAnd...\1",pokemon.name,oldmovename))
         Kernel.pbMessage(_INTL("\\se[]{1} learned {2}!\\se[Pkmn move learnt]",pokemon.name,newmovename))
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
"getForm"=>proc{|pokemon|
   next 0 if pokemon.hp<=0 || pokemon.status==PBStatuses::FROZEN ||
             PBDayNight.isNight?
   next nil
}
})

MultipleForms.register(:ARCEUS,{
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
}
})

MultipleForms.register(:DEERLING,{
"getForm"=>proc{|pokemon|
   next pbGetSeason
}
})

MultipleForms.copy(:DEERLING,:SAWSBUCK)

MultipleForms.register(:KELDEO,{
"getForm"=>proc{|pokemon|
   next 1 if pokemon.hasMove?(:SECRETSWORD) # Resolute Form
   next 0                                   # Ordinary Form
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
}
})

MultipleForms.copy(:SCATTERBUG,:SPEWPA,:VIVILLON)

MultipleForms.register(:FLABEBE,{
"getFormOnCreation"=>proc{|pokemon|
   next rand(5)
}
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

MultipleForms.register(:PUMPKABOO,{
"getFormOnCreation"=>proc{|pokemon|
   r = rand(20)
   if r==0;    next 3   # Super Size (5%)
   elsif r<4;  next 2   # Large (15%)
   elsif r<13; next 1   # Average (45%)
   end
   next 0               # Small (35%)
}
})

MultipleForms.copy(:PUMPKABOO,:GOURGEIST)

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
"onSetForm"=>proc{|pokemon,form|
   pokemon.formTime=(form>0) ? pbGetTimeNow.to_i : nil
}
})