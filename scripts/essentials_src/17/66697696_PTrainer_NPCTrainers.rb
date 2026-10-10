TPSPECIES   = 0
TPLEVEL     = 1
TPITEM      = 2
TPMOVE1     = 3
TPMOVE2     = 4
TPMOVE3     = 5
TPMOVE4     = 6
TPABILITY   = 7
TPGENDER    = 8
TPFORM      = 9
TPSHINY     = 10
TPNATURE    = 11
TPIV        = 12
TPHAPPINESS = 13
TPNAME      = 14
TPSHADOW    = 15
TPBALL      = 16
TPDEFAULTS = [0,10,0,0,0,0,0,nil,nil,0,false,nil,10,70,nil,false,0]

def pbLoadTrainer(trainerid,trainername,partyid=0)
  if trainerid.is_a?(String) || trainerid.is_a?(Symbol)
    if !hasConst?(PBTrainers,trainerid)
      raise _INTL("Trainer type does not exist ({1}, {2}, ID {3})",trainerid,trainername,partyid)
    end
    trainerid=getID(PBTrainers,trainerid)
  end
  success=false
  items=[]
  party=[]
  opponent=nil
  trainers=load_data("Data/trainers.dat")
  for trainer in trainers
    name=trainer[1]
    thistrainerid=trainer[0]
    thispartyid=trainer[4]
    next if trainerid!=thistrainerid || name!=trainername || partyid!=thispartyid
    items=trainer[2].clone
    name=pbGetMessageFromHash(MessageTypes::TrainerNames,name)
    for i in RIVALNAMES
      if isConst?(trainerid,PBTrainers,i[0]) && $game_variables[i[1]]!=0
        name=$game_variables[i[1]]
      end
    end
    opponent=PokeBattle_Trainer.new(name,thistrainerid)
    opponent.setForeignID($Trainer) if $Trainer
    for poke in trainer[3]
      species=poke[TPSPECIES]
      level=poke[TPLEVEL]
      pokemon=PokeBattle_Pokemon.new(species,level,opponent)
      pokemon.forcedForm = true if poke[TPFORM]!=0 && MultipleForms.hasFunction?(pokemon.species,"getForm")
      pokemon.formNoCall=poke[TPFORM]
      pokemon.resetMoves
      pokemon.setItem(poke[TPITEM])
      if poke[TPMOVE1]>0 || poke[TPMOVE2]>0 || poke[TPMOVE3]>0 || poke[TPMOVE4]>0
        k=0
        for move in [TPMOVE1,TPMOVE2,TPMOVE3,TPMOVE4]
          pokemon.moves[k]=PBMove.new(poke[move])
          k+=1
        end
        pokemon.moves.compact!
      end
      pokemon.setAbility(poke[TPABILITY])
      pokemon.setGender(poke[TPGENDER])
      if poke[TPSHINY]   # if this is a shiny Pokémon
        pokemon.makeShiny
      else
        pokemon.makeNotShiny
      end
      pokemon.setNature(poke[TPNATURE])
      iv=poke[TPIV]
      for i in 0...6
        pokemon.iv[i]=iv&0x1F
        pokemon.ev[i]=[85,level*3/2].min
      end
      pokemon.happiness=poke[TPHAPPINESS]
      pokemon.name=poke[TPNAME] if poke[TPNAME] && poke[TPNAME]!=""
      if poke[TPSHADOW]   # if this is a Shadow Pokémon
        pokemon.makeShadow rescue nil
        pokemon.pbUpdateShadowMoves(true) rescue nil
        pokemon.makeNotShiny
      end
      pokemon.ballused=poke[TPBALL]
      pokemon.calcStats
      party.push(pokemon)
    end
    success=true
    break
  end
  return success ? [opponent,items,party] : nil
end

def pbConvertTrainerData
  data=load_data("Data/trainertypes.dat")
  trainertypes=[]
  for i in 0...data.length
    record=data[i]
    if record
      trainertypes[record[0]]=record[2]
    end
  end
  MessageTypes.setMessages(MessageTypes::TrainerTypes,trainertypes)
  pbSaveTrainerTypes()
  pbSaveTrainerBattles()
end

def pbNewTrainer(trainerid,trainername,trainerparty)
  pokemon=[]
  level=TPDEFAULTS[TPLEVEL]
  for i in 1..6
    if i==1
      Kernel.pbMessage(_INTL("Please enter the first Pokémon.",i))
    else
      break if !Kernel.pbConfirmMessage(_INTL("Add another Pokémon?"))
    end
    loop do
      species=pbChooseSpeciesList
      if species<=0
        if i==1
          Kernel.pbMessage(_INTL("This trainer must have at least 1 Pokémon!"))
        else
          break
        end
      else
        params=ChooseNumberParams.new
        params.setRange(1,PBExperience::MAXLEVEL)
        params.setDefaultValue(level)
        level=Kernel.pbMessageChooseNumber(_INTL("Set the level for {1}.",
           PBSpecies.getName(species)),params)
        tempPoke=PokeBattle_Pokemon.new(species,level)
        pokemon.push([species,level,0,
           tempPoke.moves[0].id,
           tempPoke.moves[1].id,
           tempPoke.moves[2].id,
           tempPoke.moves[3].id
        ])
        break
      end
    end
  end
  trainer=[trainerid,trainername,[],pokemon,trainerparty]
  data=load_data("Data/trainers.dat")
  data.push(trainer)
  data=save_data(data,"Data/trainers.dat")
  pbConvertTrainerData
  Kernel.pbMessage(_INTL("The Trainer's data was added to the list of battles and at PBS/trainers.txt."))
  return trainer
end

def pbTrainerTypeCheck(symbol)
  ret=true
  if $DEBUG
    if !hasConst?(PBTrainers,symbol)
      ret=false
    else
      trtype=PBTrainers.const_get(symbol)
      data=load_data("Data/trainertypes.dat")
      ret=false if !data || !data[trtype]
    end
    if !ret
      if Kernel.pbConfirmMessage(_INTL("Add new trainer type {1}?",symbol))
        pbTrainerTypeEditorNew(symbol.to_s)
      end
      pbMapInterpreter.command_end if pbMapInterpreter
    end
  end
  return ret
end

def pbGetFreeTrainerParty(trainerid,trainername)
  for i in 0...256
    trainer=pbLoadTrainer(trainerid,trainername,i)
    return i if !trainer
  end
  return -1
end

def pbTrainerCheck(trainerid,trainername,maxbattles,startBattleId=0)
  if $DEBUG
    if trainerid.is_a?(String) || trainerid.is_a?(Symbol)
      pbTrainerTypeCheck(trainerid)
      return false if !hasConst?(PBTrainers,trainerid)
      trainerid=PBTrainers.const_get(trainerid)
    end
    for i in 0...maxbattles
      trainer=pbLoadTrainer(trainerid,trainername,i+startBattleId)
      if !trainer
        traineridstring="#{trainerid}"
        traineridstring=getConstantName(PBTrainers,trainerid) rescue "-"
        if Kernel.pbConfirmMessage(_INTL("Add new battle {1} (of {2}) for ({3}, {4})?",
           i+1,maxbattles,traineridstring,trainername))
          pbNewTrainer(trainerid,trainername,i)
        end
      end
    end
  end
  return true
end

def pbMissingTrainer(trainerid, trainername, trainerparty)
  if trainerid.is_a?(String) || trainerid.is_a?(Symbol)
    if !hasConst?(PBTrainers,trainerid)
      raise _INTL("Trainer type does not exist ({1}, {2}, ID {3})",trainerid,trainername,partyid)
    end
    trainerid=getID(PBTrainers,trainerid)
  end
  traineridstring="#{trainerid}"
  traineridstring=getConstantName(PBTrainers,trainerid) rescue "-"
  if $DEBUG
	  message=""
    if trainerparty!=0
      message=(_INTL("Add new trainer ({1}, {2}, ID {3})?",traineridstring,trainername,trainerparty))
    else
      message=(_INTL("Add new trainer ({1}, {2})?",traineridstring,trainername))
    end
    cmd=Kernel.pbMessage(message,[_INTL("Yes"),_INTL("No")],2)
    if cmd==0
      pbNewTrainer(trainerid,trainername,trainerparty)
    end
    return cmd
  else
    raise _INTL("Can't find trainer ({1}, {2}, ID {3})",traineridstring,trainername,trainerparty)
  end
end



#===============================================================================
# Walking charset, for use in text entry screens and load game screen
#===============================================================================
class TrainerWalkingCharSprite < SpriteWrapper
  def initialize(charset,viewport=nil)
    super(viewport)
    @animbitmap=nil
    self.charset=charset
    @animframe=0   # Current frame
    @frame=0       # Counter
    @frameskip=6   # Animation speed
  end

  def charset=(value)
    @animbitmap.dispose if @animbitmap
    @animbitmap=nil
    bitmapFileName=sprintf("Graphics/Characters/%s",value)
    @charset=pbResolveBitmap(bitmapFileName)
    if @charset
      @animbitmap=AnimatedBitmap.new(@charset)
      self.bitmap=@animbitmap.bitmap
      self.src_rect.set(0,0,self.bitmap.width/4,self.bitmap.height/4)
    else
      self.bitmap=nil
    end
  end

  def altcharset=(value)   # Used for box icon in the naming screen
    @animbitmap.dispose if @animbitmap
    @animbitmap=nil
    @charset=pbResolveBitmap(value)
    if @charset
      @animbitmap=AnimatedBitmap.new(@charset)
      self.bitmap=@animbitmap.bitmap
      self.src_rect.set(0,0,self.bitmap.width/4,self.bitmap.height)
    else
      self.bitmap=nil
    end
  end

  def animspeed=(value)
    @frameskip=value
  end

  def dispose
    @animbitmap.dispose if @animbitmap
    super
  end

  def update
    @updating=true
    super
    if @animbitmap
      @animbitmap.update
      self.bitmap=@animbitmap.bitmap 
    end
    @frame+=1
    @frame=0 if @frame>100
    if @frame>=@frameskip
      @animframe=(@animframe+1)%4
      self.src_rect.x=@animframe*@animbitmap.bitmap.width/4
      @frame=0
    end
    @updating=false
  end
end