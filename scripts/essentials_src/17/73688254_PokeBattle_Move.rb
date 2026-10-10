class PokeBattle_Move
  attr_accessor(:id)
  attr_reader(:battle)
  attr_reader(:name)
  attr_reader(:function)
  attr_reader(:basedamage)
  attr_reader(:type)
  attr_reader(:accuracy)
  attr_reader(:addlEffect)
  attr_reader(:target)
  attr_reader(:priority)
  attr_reader(:flags)
  attr_reader(:thismove)
  attr_accessor(:pp)
  attr_accessor(:totalpp)

  NOTYPE          = 0x01
  IGNOREPKMNTYPES = 0x02
  NOWEIGHTING     = 0x04
  NOCRITICAL      = 0x08
  NOREFLECT       = 0x10
  SELFCONFUSE     = 0x20

################################################################################
# Creating a move
################################################################################
  def initialize(battle,move)
    @id = move.id
    @battle = battle
    @name = PBMoves.getName(id)   # Get the move's name
    # Get data on the move
    movedata = PBMoveData.new(id)
    @function   = movedata.function
    @basedamage = movedata.basedamage
    @type       = movedata.type
    @accuracy   = movedata.accuracy
    @addlEffect = movedata.addlEffect
    @target     = movedata.target
    @priority   = movedata.priority
    @flags      = movedata.flags
    @category   = movedata.category
    @thismove   = move
    @pp         = move.pp   # Can be changed with Mimic/Transform
    @powerboost = false   # For Aerilate, Pixilate, Refrigerate
  end

# This is the code actually used to generate a PokeBattle_Move object.  The
# object generated is a subclass of this one which depends on the move's
# function code (found in the script section PokeBattle_MoveEffect).
  def PokeBattle_Move.pbFromPBMove(battle,move)
    move=PBMove.new(0) if !move
    movedata=PBMoveData.new(move.id)
    className=sprintf("PokeBattle_Move_%03X",movedata.function)
    if Object.const_defined?(className)
      return Kernel.const_get(className).new(battle,move)
    else
      return PokeBattle_UnimplementedMove.new(battle,move)
    end
  end

################################################################################
# About the move
################################################################################
  def totalpp
    return @totalpp if @totalpp && @totalpp>0
    return @thismove.totalpp if @thismove
    return 0
  end

  def addlEffect
    return @addlEffect
  end

  def to_int
    return @id
  end

  def pbModifyType(type,attacker,opponent)
    if type>=0
      if attacker.hasWorkingAbility(:NORMALIZE) && hasConst?(PBTypes,:NORMAL)
        type=getConst(PBTypes,:NORMAL)
      elsif isConst?(type,PBTypes,:NORMAL)
        if attacker.hasWorkingAbility(:AERILATE) && hasConst?(PBTypes,:FLYING)
          type=getConst(PBTypes,:FLYING)
          @powerboost=true
        elsif attacker.hasWorkingAbility(:REFRIGERATE) && hasConst?(PBTypes,:ICE)
          type=getConst(PBTypes,:ICE)
          @powerboost=true
        elsif attacker.hasWorkingAbility(:PIXILATE) && hasConst?(PBTypes,:FAIRY)
          type=getConst(PBTypes,:FAIRY)
          @powerboost=true
        end
      end
    end
    return type
  end

  def pbType(type,attacker,opponent)
    @powerboost=false
    type=pbModifyType(type,attacker,opponent)
    if type>=0 && hasConst?(PBTypes,:ELECTRIC)
      if @battle.field.effects[PBEffects::IonDeluge] && isConst?(type,PBTypes,:NORMAL)
        type=getConst(PBTypes,:ELECTRIC)
        @powerboost=false
      end
      if attacker.effects[PBEffects::Electrify]
        type=getConst(PBTypes,:ELECTRIC)
        @powerboost=false
      end
    end
    return type
  end

  def pbIsPhysical?(type)
    if USEMOVECATEGORY
      return @category==0
    else
      return !PBTypes.isSpecialType?(type)
    end
  end

  def pbIsSpecial?(type)
    if USEMOVECATEGORY
      return @category==1
    else
      return PBTypes.isSpecialType?(type)
    end
  end

  def pbIsStatus?
    return @category==2
  end

  def pbIsDamaging?
    return !pbIsStatus?
  end

  def pbTargetsMultiple?(attacker)
    numtargets=0
    if @target==PBTargets::AllOpposing
      # TODO: should apply even if partner faints during an attack
      numtargets+=1 if !attacker.pbOpposing1.fainted?
      numtargets+=1 if !attacker.pbOpposing2.fainted?
      return numtargets>1
    elsif @target==PBTargets::AllNonUsers
      # TODO: should apply even if partner faints during an attack
      numtargets+=1 if !attacker.pbOpposing1.fainted?
      numtargets+=1 if !attacker.pbOpposing2.fainted?
      numtargets+=1 if !attacker.pbPartner.fainted?
      return numtargets>1
    end
    return false
  end

  def pbPriority(attacker)
    ret=@priority
    return ret
  end

  def pbNumHits(attacker)
    # Parental Bond goes here (for single target moves only)
    if attacker.hasWorkingAbility(:PARENTALBOND)
      if pbIsDamaging? && !pbTargetsMultiple?(attacker) &&
         !pbIsMultiHit && !pbTwoTurnAttack(attacker)
        exceptions=[0x6E,   # Endeavor
                    0xE0,   # Selfdestruct/Explosion
                    0xE1,   # Final Gambit
                    0xF7]   # Fling
        if !exceptions.include?(@function)
          attacker.effects[PBEffects::ParentalBond]=3
          return 2
        end
      end
    end
    # Need to record that Parental Bond applies, to weaken the second attack
    return 1
  end

  def pbIsMultiHit   # not the same as pbNumHits>1
    return false
  end

  def pbTwoTurnAttack(attacker)
    return false
  end

  def pbAdditionalEffect(attacker,opponent)
  end

  def pbCanUseWhileAsleep?
    return false
  end

  def isHealingMove?
    return false
  end

  def isRecoilMove?
    return false
  end

  def unusableInGravity?
    return false
  end

  def isContactMove?
    return (@flags&0x01)!=0 # flag a: Makes contact
  end

  def canProtectAgainst?
    return (@flags&0x02)!=0 # flag b: Protect/Detect
  end

  def canMagicCoat?
    return (@flags&0x04)!=0 # flag c: Magic Coat
  end

  def canSnatch?
    return (@flags&0x08)!=0 # flag d: Snatch
  end

  def canMirrorMove? # This method isn't used
    return (@flags&0x10)!=0 # flag e: Copyable by Mirror Move
  end

  def canKingsRock?
    return (@flags&0x20)!=0 # flag f: King's Rock
  end

  def canThawUser?
    return (@flags&0x40)!=0 # flag g: Thaws user before moving
  end

  def hasHighCriticalRate?
    return (@flags&0x80)!=0 # flag h: Has high critical hit rate
  end

  def isBitingMove?
    return (@flags&0x100)!=0 # flag i: Is biting move
  end

  def isPunchingMove?
    return (@flags&0x200)!=0 # flag j: Is punching move
  end

  def isSoundBased?
    return (@flags&0x400)!=0 # flag k: Is sound-based move
  end

  def isPowderMove?
    return (@flags&0x800)!=0 # flag l: Is powder move
  end

  def isPulseMove?
    return (@flags&0x1000)!=0 # flag m: Is pulse move
  end

  def isBombMove?
    return (@flags&0x2000)!=0 # flag n: Is bomb move
  end

  def tramplesMinimize?(param=1) # Causes perfect accuracy and double damage
    return false if !USENEWBATTLEMECHANICS
    return isConst?(@id,PBMoves,:BODYSLAM) ||
           isConst?(@id,PBMoves,:FLYINGPRESS) ||
           isConst?(@id,PBMoves,:PHANTOMFORCE)
  end

  def successCheckPerHit?
    return false
  end

  def ignoresSubstitute?(attacker)
    if USENEWBATTLEMECHANICS
      return true if isSoundBased?
      return true if attacker && attacker.hasWorkingAbility(:INFILTRATOR)
    end
    return false
  end

################################################################################
# This move's type effectiveness
################################################################################
  def pbTypeImmunityByAbility(type,attacker,opponent)
    return false if attacker.index==opponent.index
    return false if attacker.hasMoldBreaker
    if opponent.hasWorkingAbility(:SAPSIPPER) && isConst?(type,PBTypes,:GRASS)
      PBDebug.log("[Ability triggered] #{opponent.pbThis}'s Sap Sipper (made #{@name} ineffective)")
      if opponent.pbCanIncreaseStatStage?(PBStats::ATTACK,opponent)
        opponent.pbIncreaseStatWithCause(PBStats::ATTACK,1,opponent,PBAbilities.getName(opponent.ability))
      else
        @battle.pbDisplay(_INTL("{1}'s {2} made {3} ineffective!",
           opponent.pbThis,PBAbilities.getName(opponent.ability),self.name))
      end
      return true
    end
    if (opponent.hasWorkingAbility(:STORMDRAIN) && isConst?(type,PBTypes,:WATER)) ||
       (opponent.hasWorkingAbility(:LIGHTNINGROD) && isConst?(type,PBTypes,:ELECTRIC))
      PBDebug.log("[Ability triggered] #{opponent.pbThis}'s #{PBAbilities.getName(opponent.ability)} (made #{@name} ineffective)")
      if opponent.pbCanIncreaseStatStage?(PBStats::SPATK,opponent)
        opponent.pbIncreaseStatWithCause(PBStats::SPATK,1,opponent,PBAbilities.getName(opponent.ability))
      else
        @battle.pbDisplay(_INTL("{1}'s {2} made {3} ineffective!",
           opponent.pbThis,PBAbilities.getName(opponent.ability),self.name))
      end
      return true
    end
    if opponent.hasWorkingAbility(:MOTORDRIVE) && isConst?(type,PBTypes,:ELECTRIC)
      PBDebug.log("[Ability triggered] #{opponent.pbThis}'s Motor Drive (made #{@name} ineffective)")
      if opponent.pbCanIncreaseStatStage?(PBStats::SPEED,opponent)
        opponent.pbIncreaseStatWithCause(PBStats::SPEED,1,opponent,PBAbilities.getName(opponent.ability))
      else
        @battle.pbDisplay(_INTL("{1}'s {2} made {3} ineffective!",
           opponent.pbThis,PBAbilities.getName(opponent.ability),self.name))
      end
      return true
    end
    if (opponent.hasWorkingAbility(:DRYSKIN) && isConst?(type,PBTypes,:WATER)) ||
       (opponent.hasWorkingAbility(:VOLTABSORB) && isConst?(type,PBTypes,:ELECTRIC)) ||
       (opponent.hasWorkingAbility(:WATERABSORB) && isConst?(type,PBTypes,:WATER))
      PBDebug.log("[Ability triggered] #{opponent.pbThis}'s #{PBAbilities.getName(opponent.ability)} (made #{@name} ineffective)")
      healed=false
      if opponent.effects[PBEffects::HealBlock]==0
        if opponent.pbRecoverHP((opponent.totalhp/4).floor,true)>0
          @battle.pbDisplay(_INTL("{1}'s {2} restored its HP!",
             opponent.pbThis,PBAbilities.getName(opponent.ability)))
        end
      end
      if !healed
        @battle.pbDisplay(_INTL("{1}'s {2} made {3} useless!",
           opponent.pbThis,PBAbilities.getName(opponent.ability),@name))
      end
      return true
    end
    if opponent.hasWorkingAbility(:FLASHFIRE) && isConst?(type,PBTypes,:FIRE)
      PBDebug.log("[Ability triggered] #{opponent.pbThis}'s Flash Fire (made #{@name} ineffective)")
      if !opponent.effects[PBEffects::FlashFire]
        opponent.effects[PBEffects::FlashFire]=true
        @battle.pbDisplay(_INTL("{1}'s {2} raised its Fire power!",
           opponent.pbThis,PBAbilities.getName(opponent.ability)))
      else
        @battle.pbDisplay(_INTL("{1}'s {2} made {3} ineffective!",
           opponent.pbThis,PBAbilities.getName(opponent.ability),self.name))
      end
      return true
    end
    if opponent.hasWorkingAbility(:TELEPATHY) && pbIsDamaging? &&
       !opponent.pbIsOpposing?(attacker.index)
      PBDebug.log("[Ability triggered] #{opponent.pbThis}'s Telepathy (made #{@name} ineffective)")
      @battle.pbDisplay(_INTL("{1} avoids attacks by its ally Pokémon!",opponent.pbThis))
      return true
    end
    if opponent.hasWorkingAbility(:BULLETPROOF) && isBombMove?
      PBDebug.log("[Ability triggered] #{opponent.pbThis}'s Bulletproof (made #{@name} ineffective)")
      @battle.pbDisplay(_INTL("{1}'s {2} made {3} ineffective!",
         opponent.pbThis,PBAbilities.getName(opponent.ability),self.name))
      return true
    end
    return false
  end

  def pbTypeModifier(type,attacker,opponent)
    return 8 if type<0
    return 8 if isConst?(type,PBTypes,:GROUND) && opponent.pbHasType?(:FLYING) &&
                opponent.hasWorkingItem(:IRONBALL) && !USENEWBATTLEMECHANICS
    atype=type # attack type
    otype1=opponent.type1
    otype2=opponent.type2
    otype3=opponent.effects[PBEffects::Type3] || -1
    # Roost
    if isConst?(otype1,PBTypes,:FLYING) && opponent.effects[PBEffects::Roost]
      if isConst?(otype2,PBTypes,:FLYING) && isConst?(otype3,PBTypes,:FLYING)
        otype1=getConst(PBTypes,:NORMAL) || 0
      else
        otype1=otype2
      end
    end
    if isConst?(otype2,PBTypes,:FLYING) && opponent.effects[PBEffects::Roost]
      otype2=otype1
    end
    # Get effectivenesses
    mod1=PBTypes.getEffectiveness(atype,otype1)
    mod2=(otype1==otype2) ? 2 : PBTypes.getEffectiveness(atype,otype2)
    mod3=(otype3<0 || otype1==otype3 || otype2==otype3) ? 2 : PBTypes.getEffectiveness(atype,otype3)
    if opponent.hasWorkingItem(:RINGTARGET)
      mod1=2 if mod1==0
      mod2=2 if mod2==0
      mod3=2 if mod3==0
    end
    # Foresight
    if attacker.hasWorkingAbility(:SCRAPPY) || opponent.effects[PBEffects::Foresight]
      mod1=2 if isConst?(otype1,PBTypes,:GHOST) && PBTypes.isIneffective?(atype,otype1)
      mod2=2 if isConst?(otype2,PBTypes,:GHOST) && PBTypes.isIneffective?(atype,otype2)
      mod3=2 if isConst?(otype3,PBTypes,:GHOST) && PBTypes.isIneffective?(atype,otype3)
    end
    # Miracle Eye
    if opponent.effects[PBEffects::MiracleEye]
      mod1=2 if isConst?(otype1,PBTypes,:DARK) && PBTypes.isIneffective?(atype,otype1)
      mod2=2 if isConst?(otype2,PBTypes,:DARK) && PBTypes.isIneffective?(atype,otype2)
      mod3=2 if isConst?(otype3,PBTypes,:DARK) && PBTypes.isIneffective?(atype,otype3)
    end
    # Delta Stream's weather
    if @battle.pbWeather==PBWeather::STRONGWINDS
      mod1=2 if isConst?(otype1,PBTypes,:FLYING) && PBTypes.isSuperEffective?(atype,otype1)
      mod2=2 if isConst?(otype2,PBTypes,:FLYING) && PBTypes.isSuperEffective?(atype,otype2)
      mod3=2 if isConst?(otype3,PBTypes,:FLYING) && PBTypes.isSuperEffective?(atype,otype3)
    end
    # Smack Down makes Ground moves work against fliers
    if (!opponent.isAirborne?(attacker.hasMoldBreaker) || @function==0x11C) && # Smack Down
       isConst?(atype,PBTypes,:GROUND)
      mod1=2 if isConst?(otype1,PBTypes,:FLYING)
      mod2=2 if isConst?(otype2,PBTypes,:FLYING)
      mod3=2 if isConst?(otype3,PBTypes,:FLYING)
    end
    if @function==0x135 && !attacker.effects[PBEffects::Electrify] # Freeze-Dry
      mod1=4 if isConst?(otype1,PBTypes,:WATER)
      if isConst?(otype2,PBTypes,:WATER)
        mod2=(otype1==otype2) ? 2 : 4
      end
      if isConst?(otype3,PBTypes,:WATER)
        mod3=(otype1==otype3 || otype2==otype3) ? 2 : 4
      end
    end
    return mod1*mod2*mod3
  end

  def pbTypeModMessages(type,attacker,opponent)
    return 8 if type<0
    typemod=pbTypeModifier(type,attacker,opponent)
    if typemod==0
      @battle.pbDisplay(_INTL("It doesn't affect {1}...",opponent.pbThis(true)))
    else
      return 0 if pbTypeImmunityByAbility(type,attacker,opponent)
    end
    return typemod
  end

################################################################################
# This move's accuracy check
################################################################################
  def pbModifyBaseAccuracy(baseaccuracy,attacker,opponent)
    return baseaccuracy
  end

  def pbAccuracyCheck(attacker,opponent)
    baseaccuracy=@accuracy
    baseaccuracy=pbModifyBaseAccuracy(baseaccuracy,attacker,opponent)
    baseaccuracy=0 if opponent.effects[PBEffects::Minimize] && tramplesMinimize?(1)
    return true if baseaccuracy==0
    return true if attacker.hasWorkingAbility(:NOGUARD) ||
                   opponent.hasWorkingAbility(:NOGUARD)
    return true if opponent.hasWorkingAbility(:STORMDRAIN) &&
                   isConst?(pbType(@type,attacker,opponent),PBTypes,:WATER)
    return true if opponent.hasWorkingAbility(:LIGHTNINGROD) &&
                   isConst?(pbType(@type,attacker,opponent),PBTypes,:ELECTRIC)
    return true if opponent.effects[PBEffects::Telekinesis]>0
    # One-hit KO accuracy handled elsewhere
    accstage=attacker.stages[PBStats::ACCURACY]
    accstage=0 if !attacker.hasMoldBreaker && opponent.hasWorkingAbility(:UNAWARE)
    accuracy=(accstage>=0) ? (accstage+3)*100.0/3 : 300.0/(3-accstage)
    evastage=opponent.stages[PBStats::EVASION]
    evastage-=2 if @battle.field.effects[PBEffects::Gravity]>0
    evastage=-6 if evastage<-6
    evastage=0 if evastage>0 && USENEWBATTLEMECHANICS &&
                  attacker.hasWorkingAbility(:KEENEYE)
    evastage=0 if opponent.effects[PBEffects::Foresight] ||
                  opponent.effects[PBEffects::MiracleEye] ||
                  @function==0xA9 || # Chip Away
                  attacker.hasWorkingAbility(:UNAWARE)
    evasion=(evastage>=0) ? (evastage+3)*100.0/3 : 300.0/(3-evastage)
    if attacker.hasWorkingAbility(:COMPOUNDEYES)
      accuracy*=1.3
    end
    if attacker.hasWorkingAbility(:HUSTLE) && pbIsDamaging? &&
       pbIsPhysical?(pbType(@type,attacker,opponent))
      accuracy*=0.8
    end
    if attacker.hasWorkingAbility(:VICTORYSTAR)
      accuracy*=1.1
    end
    partner=attacker.pbPartner
    if partner && partner.hasWorkingAbility(:VICTORYSTAR)
      accuracy*=1.1
    end
    if attacker.effects[PBEffects::MicleBerry]
      attacker.effects[PBEffects::MicleBerry]=false
      accuracy*=1.2
    end
    if attacker.hasWorkingItem(:WIDELENS)
      accuracy*=1.1
    end
    if attacker.hasWorkingItem(:ZOOMLENS) &&
       (@battle.choices[opponent.index][0]!=1 || # Didn't choose a move
       opponent.hasMovedThisRound?) # Used a move already
      accuracy*=1.2
    end
    if !attacker.hasMoldBreaker
      if opponent.hasWorkingAbility(:WONDERSKIN) && pbIsStatus? &&
         attacker.pbIsOpposing?(opponent.index)
        accuracy=50 if accuracy>50
      end
      if opponent.hasWorkingAbility(:TANGLEDFEET) &&
         opponent.effects[PBEffects::Confusion]>0
        evasion*=1.2
      end
      if opponent.hasWorkingAbility(:SANDVEIL) &&
         @battle.pbWeather==PBWeather::SANDSTORM
        evasion*=1.25
      end
      if opponent.hasWorkingAbility(:SNOWCLOAK) &&
         @battle.pbWeather==PBWeather::HAIL
        evasion*=1.25
      end
    end
    if opponent.hasWorkingItem(:BRIGHTPOWDER)
      evasion*=1.1
    end
    if opponent.hasWorkingItem(:LAXINCENSE)
      evasion*=1.1
    end
    return @battle.pbRandom(100)<(baseaccuracy*accuracy/evasion)
  end

################################################################################
# Damage calculation and modifiers
################################################################################
  def pbCritialOverride(attacker,opponent)
    return false
  end

  def pbIsCritical?(attacker,opponent)
    if !attacker.hasMoldBreaker
      if opponent.hasWorkingAbility(:BATTLEARMOR) ||
         opponent.hasWorkingAbility(:SHELLARMOR)
        return false
      end
    end
    return false if opponent.pbOwnSide.effects[PBEffects::LuckyChant]>0
    return true if pbCritialOverride(attacker,opponent)
    c=0
    ratios=(USENEWBATTLEMECHANICS) ? [16,8,2,1,1] : [16,8,4,3,2]
    c+=attacker.effects[PBEffects::FocusEnergy]
    c+=1 if hasHighCriticalRate?
    if (attacker.inHyperMode? rescue false) && isConst?(self.type,PBTypes,:SHADOW)
      c+=1
    end
    c+=1 if attacker.hasWorkingAbility(:SUPERLUCK)
    if attacker.hasWorkingItem(:STICK) &&
       isConst?(attacker.species,PBSpecies,:FARFETCHD)
      c+=2
    end
    if attacker.hasWorkingItem(:LUCKYPUNCH) &&
       isConst?(attacker.species,PBSpecies,:CHANSEY)
      c+=2
    end
    c+=1 if attacker.hasWorkingItem(:RAZORCLAW)
    c+=1 if attacker.hasWorkingItem(:SCOPELENS)
    c=4 if c>4
    return @battle.pbRandom(ratios[c])==0
  end

  def pbBaseDamage(basedmg,attacker,opponent)
    return basedmg
  end

  def pbBaseDamageMultiplier(damagemult,attacker,opponent)
    return damagemult
  end

  def pbModifyDamage(damagemult,attacker,opponent)
    return damagemult
  end

  def pbCalcDamage(attacker,opponent,options=0)
    opponent.damagestate.critical=false
    opponent.damagestate.typemod=0
    opponent.damagestate.calcdamage=0
    opponent.damagestate.hplost=0
    return 0 if @basedamage==0
    stagemul=[10,10,10,10,10,10,10,15,20,25,30,35,40]
    stagediv=[40,35,30,25,20,15,10,10,10,10,10,10,10]
    if (options&NOTYPE)==0
      type=pbType(@type,attacker,opponent)
    else
      type=-1 # Will be treated as physical
    end
    if (options&NOCRITICAL)==0
      opponent.damagestate.critical=pbIsCritical?(attacker,opponent)
    end
    ##### Calcuate base power of move #####
    basedmg=@basedamage # Fron PBS file
    basedmg=pbBaseDamage(basedmg,attacker,opponent) # Some function codes alter base power
    damagemult=0x1000
    if attacker.hasWorkingAbility(:TECHNICIAN) && basedmg<=60 && @id>0
      damagemult=(damagemult*1.5).round
    end
    if attacker.hasWorkingAbility(:IRONFIST) && isPunchingMove?
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingAbility(:STRONGJAW) && isBitingMove?
      damagemult=(damagemult*1.5).round
    end
    if attacker.hasWorkingAbility(:MEGALAUNCHER) && isPulseMove?
      damagemult=(damagemult*1.5).round
    end
    if attacker.hasWorkingAbility(:RECKLESS) && isRecoilMove?
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingAbility(:FLAREBOOST) &&
       attacker.status==PBStatuses::BURN && pbIsSpecial?(type)
      damagemult=(damagemult*1.5).round
    end
    if attacker.hasWorkingAbility(:TOXICBOOST) &&
       attacker.status==PBStatuses::POISON && pbIsPhysical?(type)
      damagemult=(damagemult*1.5).round
    end
    if attacker.hasWorkingAbility(:ANALYTIC) &&
       (@battle.choices[opponent.index][0]!=1 || # Didn't choose a move
       opponent.hasMovedThisRound?) # Used a move already
      damagemult=(damagemult*1.3).round
    end
    if attacker.hasWorkingAbility(:RIVALRY) &&
       attacker.gender!=2 && opponent.gender!=2
      if attacker.gender==opponent.gender
        damagemult=(damagemult*1.25).round
      else
        damagemult=(damagemult*0.75).round
      end
    end
    if attacker.hasWorkingAbility(:SANDFORCE) &&
       @battle.pbWeather==PBWeather::SANDSTORM &&
       (isConst?(type,PBTypes,:ROCK) ||
       isConst?(type,PBTypes,:GROUND) ||
       isConst?(type,PBTypes,:STEEL))
      damagemult=(damagemult*1.3).round
    end
    if attacker.hasWorkingAbility(:SHEERFORCE) && self.addlEffect>0
      damagemult=(damagemult*1.3).round
    end
    if attacker.hasWorkingAbility(:TOUGHCLAWS) && isContactMove?
      damagemult=(damagemult*4/3).round
    end
    if (attacker.hasWorkingAbility(:AERILATE) ||
       attacker.hasWorkingAbility(:REFRIGERATE) ||
       attacker.hasWorkingAbility(:PIXILATE)) && @powerboost
      damagemult=(damagemult*1.3).round
    end
    if (@battle.pbCheckGlobalAbility(:DARKAURA) && isConst?(type,PBTypes,:DARK)) ||
       (@battle.pbCheckGlobalAbility(:FAIRYAURA) && isConst?(type,PBTypes,:FAIRY))
      if @battle.pbCheckGlobalAbility(:AURABREAK)
        damagemult=(damagemult*2/3).round
      else
        damagemult=(damagemult*4/3).round
      end
    end
    if !attacker.hasMoldBreaker
      if opponent.hasWorkingAbility(:HEATPROOF) && isConst?(type,PBTypes,:FIRE)
        damagemult=(damagemult*0.5).round
      end
      if opponent.hasWorkingAbility(:THICKFAT) &&
         (isConst?(type,PBTypes,:ICE) || isConst?(type,PBTypes,:FIRE))
        damagemult=(damagemult*0.5).round
      end
      if opponent.hasWorkingAbility(:FURCOAT) &&
         (pbIsPhysical?(type) || @function==0x122) # Psyshock
        damagemult=(damagemult*0.5).round
      end
      if opponent.hasWorkingAbility(:DRYSKIN) && isConst?(type,PBTypes,:FIRE)
        damagemult=(damagemult*1.25).round
      end
    end
    # Gems are the first items to be considered, as Symbiosis can replace a
    # consumed Gem and the replacement item should work immediately.
    if @function!=0x106 && @function!=0x107 && @function!=0x108 # Pledge moves
      if (attacker.hasWorkingItem(:NORMALGEM) && isConst?(type,PBTypes,:NORMAL)) ||
         (attacker.hasWorkingItem(:FIGHTINGGEM) && isConst?(type,PBTypes,:FIGHTING)) ||
         (attacker.hasWorkingItem(:FLYINGGEM) && isConst?(type,PBTypes,:FLYING)) ||
         (attacker.hasWorkingItem(:POISONGEM) && isConst?(type,PBTypes,:POISON)) ||
         (attacker.hasWorkingItem(:GROUNDGEM) && isConst?(type,PBTypes,:GROUND)) ||
         (attacker.hasWorkingItem(:ROCKGEM) && isConst?(type,PBTypes,:ROCK)) ||
         (attacker.hasWorkingItem(:BUGGEM) && isConst?(type,PBTypes,:BUG)) ||
         (attacker.hasWorkingItem(:GHOSTGEM) && isConst?(type,PBTypes,:GHOST)) ||
         (attacker.hasWorkingItem(:STEELGEM) && isConst?(type,PBTypes,:STEEL)) ||
         (attacker.hasWorkingItem(:FIREGEM) && isConst?(type,PBTypes,:FIRE)) ||
         (attacker.hasWorkingItem(:WATERGEM) && isConst?(type,PBTypes,:WATER)) ||
         (attacker.hasWorkingItem(:GRASSGEM) && isConst?(type,PBTypes,:GRASS)) ||
         (attacker.hasWorkingItem(:ELECTRICGEM) && isConst?(type,PBTypes,:ELECTRIC)) ||
         (attacker.hasWorkingItem(:PSYCHICGEM) && isConst?(type,PBTypes,:PSYCHIC)) ||
         (attacker.hasWorkingItem(:ICEGEM) && isConst?(type,PBTypes,:ICE)) ||
         (attacker.hasWorkingItem(:DRAGONGEM) && isConst?(type,PBTypes,:DRAGON)) ||
         (attacker.hasWorkingItem(:DARKGEM) && isConst?(type,PBTypes,:DARK)) ||
         (attacker.hasWorkingItem(:FAIRYGEM) && isConst?(type,PBTypes,:FAIRY))
        damagemult=(USENEWBATTLEMECHANICS) ? (damagemult*1.3).round : (damagemult*1.5).round
        @battle.pbCommonAnimation("UseItem",attacker,nil)
        @battle.pbDisplayBrief(_INTL("The {1} strengthened {2}'s power!",
           PBItems.getName(attacker.item),@name))
        attacker.pbConsumeItem
      end
    end
    if (attacker.hasWorkingItem(:SILKSCARF) && isConst?(type,PBTypes,:NORMAL)) ||
       (attacker.hasWorkingItem(:BLACKBELT) && isConst?(type,PBTypes,:FIGHTING)) ||
       (attacker.hasWorkingItem(:SHARPBEAK) && isConst?(type,PBTypes,:FLYING)) ||
       (attacker.hasWorkingItem(:POISONBARB) && isConst?(type,PBTypes,:POISON)) ||
       (attacker.hasWorkingItem(:SOFTSAND) && isConst?(type,PBTypes,:GROUND)) ||
       (attacker.hasWorkingItem(:HARDSTONE) && isConst?(type,PBTypes,:ROCK)) ||
       (attacker.hasWorkingItem(:SILVERPOWDER) && isConst?(type,PBTypes,:BUG)) ||
       (attacker.hasWorkingItem(:SPELLTAG) && isConst?(type,PBTypes,:GHOST)) ||
       (attacker.hasWorkingItem(:METALCOAT) && isConst?(type,PBTypes,:STEEL)) ||
       (attacker.hasWorkingItem(:CHARCOAL) && isConst?(type,PBTypes,:FIRE)) ||
       (attacker.hasWorkingItem(:MYSTICWATER) && isConst?(type,PBTypes,:WATER)) ||
       (attacker.hasWorkingItem(:MIRACLESEED) && isConst?(type,PBTypes,:GRASS)) ||
       (attacker.hasWorkingItem(:MAGNET) && isConst?(type,PBTypes,:ELECTRIC)) ||
       (attacker.hasWorkingItem(:TWISTEDSPOON) && isConst?(type,PBTypes,:PSYCHIC)) ||
       (attacker.hasWorkingItem(:NEVERMELTICE) && isConst?(type,PBTypes,:ICE)) ||
       (attacker.hasWorkingItem(:DRAGONFANG) && isConst?(type,PBTypes,:DRAGON)) ||
       (attacker.hasWorkingItem(:BLACKGLASSES) && isConst?(type,PBTypes,:DARK))
      damagemult=(damagemult*1.2).round
    end
    if (attacker.hasWorkingItem(:FISTPLATE) && isConst?(type,PBTypes,:FIGHTING)) ||
       (attacker.hasWorkingItem(:SKYPLATE) && isConst?(type,PBTypes,:FLYING)) ||
       (attacker.hasWorkingItem(:TOXICPLATE) && isConst?(type,PBTypes,:POISON)) ||
       (attacker.hasWorkingItem(:EARTHPLATE) && isConst?(type,PBTypes,:GROUND)) ||
       (attacker.hasWorkingItem(:STONEPLATE) && isConst?(type,PBTypes,:ROCK)) ||
       (attacker.hasWorkingItem(:INSECTPLATE) && isConst?(type,PBTypes,:BUG)) ||
       (attacker.hasWorkingItem(:SPOOKYPLATE) && isConst?(type,PBTypes,:GHOST)) ||
       (attacker.hasWorkingItem(:IRONPLATE) && isConst?(type,PBTypes,:STEEL)) ||
       (attacker.hasWorkingItem(:FLAMEPLATE) && isConst?(type,PBTypes,:FIRE)) ||
       (attacker.hasWorkingItem(:SPLASHPLATE) && isConst?(type,PBTypes,:WATER)) ||
       (attacker.hasWorkingItem(:MEADOWPLATE) && isConst?(type,PBTypes,:GRASS)) ||
       (attacker.hasWorkingItem(:ZAPPLATE) && isConst?(type,PBTypes,:ELECTRIC)) ||
       (attacker.hasWorkingItem(:MINDPLATE) && isConst?(type,PBTypes,:PSYCHIC)) ||
       (attacker.hasWorkingItem(:ICICLEPLATE) && isConst?(type,PBTypes,:ICE)) ||
       (attacker.hasWorkingItem(:DRACOPLATE) && isConst?(type,PBTypes,:DRAGON)) ||
       (attacker.hasWorkingItem(:DREADPLATE) && isConst?(type,PBTypes,:DARK)) ||
       (attacker.hasWorkingItem(:PIXIEPLATE) && isConst?(type,PBTypes,:FAIRY))
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:ROCKINCENSE) && isConst?(type,PBTypes,:ROCK)
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:ROSEINCENSE) && isConst?(type,PBTypes,:GRASS)
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:SEAINCENSE) && isConst?(type,PBTypes,:WATER)
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:WAVEINCENSE) && isConst?(type,PBTypes,:WATER)
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:ODDINCENSE) && isConst?(type,PBTypes,:PSYCHIC)
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:MUSCLEBAND) && pbIsPhysical?(type)
      damagemult=(damagemult*1.1).round
    end
    if attacker.hasWorkingItem(:WISEGLASSES) && pbIsSpecial?(type)
      damagemult=(damagemult*1.1).round
    end
    if attacker.hasWorkingItem(:LUSTROUSORB) &&
       isConst?(attacker.species,PBSpecies,:PALKIA) &&
       (isConst?(type,PBTypes,:DRAGON) || isConst?(type,PBTypes,:WATER))
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:ADAMANTORB) &&
       isConst?(attacker.species,PBSpecies,:DIALGA) &&
       (isConst?(type,PBTypes,:DRAGON) || isConst?(type,PBTypes,:STEEL))
      damagemult=(damagemult*1.2).round
    end
    if attacker.hasWorkingItem(:GRISEOUSORB) &&
       isConst?(attacker.species,PBSpecies,:GIRATINA) &&
       (isConst?(type,PBTypes,:DRAGON) || isConst?(type,PBTypes,:GHOST))
      damagemult=(damagemult*1.2).round
    end
    damagemult=pbBaseDamageMultiplier(damagemult,attacker,opponent)
    if attacker.effects[PBEffects::MeFirst]
      damagemult=(damagemult*1.5).round
    end
    if attacker.effects[PBEffects::HelpingHand] && (options&SELFCONFUSE)==0
      damagemult=(damagemult*1.5).round
    end
    if attacker.effects[PBEffects::Charge]>0 && isConst?(type,PBTypes,:ELECTRIC)
      damagemult=(damagemult*2.0).round
    end
    if isConst?(type,PBTypes,:FIRE)
      for i in 0...4
        if @battle.battlers[i].effects[PBEffects::WaterSport] && !@battle.battlers[i].fainted?
          damagemult=(damagemult*0.33).round
          break
        end
      end
      if @battle.field.effects[PBEffects::WaterSportField]>0
        damagemult=(damagemult*0.33).round
      end
    end
    if isConst?(type,PBTypes,:ELECTRIC)
      for i in 0...4
        if @battle.battlers[i].effects[PBEffects::MudSport] && !@battle.battlers[i].fainted?
          damagemult=(damagemult*0.33).round
          break
        end
      end
      if @battle.field.effects[PBEffects::MudSportField]>0
        damagemult=(damagemult*0.33).round
      end
    end
    if @battle.field.effects[PBEffects::ElectricTerrain]>0 &&
       !attacker.isAirborne? && isConst?(type,PBTypes,:ELECTRIC)
      damagemult=(damagemult*1.5).round
    end
    if @battle.field.effects[PBEffects::GrassyTerrain]>0 &&
       !attacker.isAirborne? && isConst?(type,PBTypes,:GRASS)
      damagemult=(damagemult*1.5).round
    end
    if @battle.field.effects[PBEffects::MistyTerrain]>0 &&
       !opponent.isAirborne?(attacker.hasMoldBreaker) && isConst?(type,PBTypes,:DRAGON)
      damagemult=(damagemult*0.5).round
    end
    if opponent.effects[PBEffects::Minimize] && tramplesMinimize?(2)
      damagemult=(damagemult*2.0).round
    end
    basedmg=(basedmg*damagemult*1.0/0x1000).round
    ##### Calculate attacker's attack stat #####
    atk=attacker.attack
    atkstage=attacker.stages[PBStats::ATTACK]+6
    if @function==0x121 # Foul Play
      atk=opponent.attack
      atkstage=opponent.stages[PBStats::ATTACK]+6
    end
    if type>=0 && pbIsSpecial?(type)
      atk=attacker.spatk
      atkstage=attacker.stages[PBStats::SPATK]+6
      if @function==0x121 # Foul Play
        atk=opponent.spatk
        atkstage=opponent.stages[PBStats::SPATK]+6
      end
    end
    if attacker.hasMoldBreaker || !opponent.hasWorkingAbility(:UNAWARE)
      atkstage=6 if opponent.damagestate.critical && atkstage<6
      atk=(atk*1.0*stagemul[atkstage]/stagediv[atkstage]).floor
    end
    if attacker.hasWorkingAbility(:HUSTLE) && pbIsPhysical?(type)
      atk=(atk*1.5).round
    end
    atkmult=0x1000
    if @battle.internalbattle
      if @battle.pbOwnedByPlayer?(attacker.index) && pbIsPhysical?(type) &&
         @battle.pbPlayer.numbadges>=BADGESBOOSTATTACK
        atkmult=(atkmult*1.1).round
      end
      if @battle.pbOwnedByPlayer?(attacker.index) && pbIsSpecial?(type) &&
         @battle.pbPlayer.numbadges>=BADGESBOOSTSPATK
        atkmult=(atkmult*1.1).round
      end
    end
    if attacker.hp<=(attacker.totalhp/3).floor
      if (attacker.hasWorkingAbility(:OVERGROW) && isConst?(type,PBTypes,:GRASS)) ||
         (attacker.hasWorkingAbility(:BLAZE) && isConst?(type,PBTypes,:FIRE)) ||
         (attacker.hasWorkingAbility(:TORRENT) && isConst?(type,PBTypes,:WATER)) ||
         (attacker.hasWorkingAbility(:SWARM) && isConst?(type,PBTypes,:BUG))
        atkmult=(atkmult*1.5).round
      end
    end
    if attacker.hasWorkingAbility(:GUTS) &&
       attacker.status!=0 && pbIsPhysical?(type)
      atkmult=(atkmult*1.5).round
    end
    if (attacker.hasWorkingAbility(:PLUS) || attacker.hasWorkingAbility(:MINUS)) &&
       pbIsSpecial?(type)
      partner=attacker.pbPartner
      if partner.hasWorkingAbility(:PLUS) || partner.hasWorkingAbility(:MINUS)
        atkmult=(atkmult*1.5).round
      end
    end
    if attacker.hasWorkingAbility(:DEFEATIST) &&
       attacker.hp<=(attacker.totalhp/2).floor
      atkmult=(atkmult*0.5).round
    end
    if (attacker.hasWorkingAbility(:PUREPOWER) ||
       attacker.hasWorkingAbility(:HUGEPOWER)) && pbIsPhysical?(type)
      atkmult=(atkmult*2.0).round
    end
    if attacker.hasWorkingAbility(:SOLARPOWER) && pbIsSpecial?(type) &&
       (@battle.pbWeather==PBWeather::SUNNYDAY ||
       @battle.pbWeather==PBWeather::HARSHSUN)
      atkmult=(atkmult*1.5).round
    end
    if attacker.hasWorkingAbility(:FLASHFIRE) &&
       attacker.effects[PBEffects::FlashFire] && isConst?(type,PBTypes,:FIRE)
      atkmult=(atkmult*1.5).round
    end
    if attacker.hasWorkingAbility(:SLOWSTART) &&
       attacker.turncount<=5 && pbIsPhysical?(type)
      atkmult=(atkmult*0.5).round
    end
    if (@battle.pbWeather==PBWeather::SUNNYDAY ||
       @battle.pbWeather==PBWeather::HARSHSUN) && pbIsPhysical?(type)
      if attacker.hasWorkingAbility(:FLOWERGIFT) ||
         attacker.pbPartner.hasWorkingAbility(:FLOWERGIFT)
        atkmult=(atkmult*1.5).round
      end
    end
    if attacker.hasWorkingItem(:THICKCLUB) &&
       (isConst?(attacker.species,PBSpecies,:CUBONE) ||
       isConst?(attacker.species,PBSpecies,:MAROWAK)) && pbIsPhysical?(type)
      atkmult=(atkmult*2.0).round
    end
    if attacker.hasWorkingItem(:DEEPSEATOOTH) &&
       isConst?(attacker.species,PBSpecies,:CLAMPERL) && pbIsSpecial?(type)
      atkmult=(atkmult*2.0).round
    end
    if attacker.hasWorkingItem(:LIGHTBALL) &&
       isConst?(attacker.species,PBSpecies,:PIKACHU)
      atkmult=(atkmult*2.0).round
    end
    if attacker.hasWorkingItem(:SOULDEW) &&
       (isConst?(attacker.species,PBSpecies,:LATIAS) ||
       isConst?(attacker.species,PBSpecies,:LATIOS)) && pbIsSpecial?(type) &&
       !@battle.rules["souldewclause"]
      atkmult=(atkmult*1.5).round
    end
    if attacker.hasWorkingItem(:CHOICEBAND) && pbIsPhysical?(type)
      atkmult=(atkmult*1.5).round
    end
    if attacker.hasWorkingItem(:CHOICESPECS) && pbIsSpecial?(type)
      atkmult=(atkmult*1.5).round
    end
    atk=(atk*atkmult*1.0/0x1000).round
    ##### Calculate opponent's defense stat #####
    defense=opponent.defense
    defstage=opponent.stages[PBStats::DEFENSE]+6
    # TODO: Wonder Room should apply around here
    applysandstorm=false
    if type>=0 && pbIsSpecial?(type) && @function!=0x122 # Psyshock
      defense=opponent.spdef
      defstage=opponent.stages[PBStats::SPDEF]+6
      applysandstorm=true
    end
    if !attacker.hasWorkingAbility(:UNAWARE)
      defstage=6 if @function==0xA9 # Chip Away (ignore stat stages)
      defstage=6 if opponent.damagestate.critical && defstage>6
      defense=(defense*1.0*stagemul[defstage]/stagediv[defstage]).floor
    end
    if @battle.pbWeather==PBWeather::SANDSTORM &&
       opponent.pbHasType?(:ROCK) && applysandstorm
      defense=(defense*1.5).round
    end
    defmult=0x1000
    if @battle.internalbattle
      if @battle.pbOwnedByPlayer?(opponent.index) && pbIsPhysical?(type) &&
         @battle.pbPlayer.numbadges>=BADGESBOOSTDEFENSE
        defmult=(defmult*1.1).round
      end
      if @battle.pbOwnedByPlayer?(opponent.index) && pbIsSpecial?(type) &&
         @battle.pbPlayer.numbadges>=BADGESBOOSTSPDEF
        defmult=(defmult*1.1).round
      end
    end
    if !attacker.hasMoldBreaker
      if opponent.hasWorkingAbility(:MARVELSCALE) &&
         opponent.status>0 && pbIsPhysical?(type)
        defmult=(defmult*1.5).round
      end
      if (@battle.pbWeather==PBWeather::SUNNYDAY ||
         @battle.pbWeather==PBWeather::HARSHSUN) && pbIsSpecial?(type)
        if opponent.hasWorkingAbility(:FLOWERGIFT) ||
           opponent.pbPartner.hasWorkingAbility(:FLOWERGIFT)
          defmult=(defmult*1.5).round
        end
      end
    end
    if opponent.hasWorkingItem(:ASSAULTVEST) && pbIsSpecial?(type)
      defmult=(defmult*1.5).round
    end
    if opponent.hasWorkingItem(:EVIOLITE)
      evos=pbGetEvolvedFormData(opponent.pokemon.fSpecies)
      if evos && evos.length>0
        defmult=(defmult*1.5).round
      end
    end
    if opponent.hasWorkingItem(:DEEPSEASCALE) &&
       isConst?(opponent.species,PBSpecies,:CLAMPERL) && pbIsSpecial?(type)
      defmult=(defmult*2.0).round
    end
    if opponent.hasWorkingItem(:METALPOWDER) &&
       isConst?(opponent.species,PBSpecies,:DITTO) &&
       !opponent.effects[PBEffects::Transform]
      defmult=(defmult*1.5).round
    end
    if opponent.hasWorkingItem(:SOULDEW) &&
       (isConst?(opponent.species,PBSpecies,:LATIAS) ||
       isConst?(opponent.species,PBSpecies,:LATIOS)) && pbIsSpecial?(type) &&
       !@battle.rules["souldewclause"]
      defmult=(defmult*1.5).round
    end
    defense=[(defense*defmult*1.0/0x1000).round,1].max
    ##### Main damage calculation #####
    damage=(((2.0*attacker.level/5+2).floor*basedmg*atk/defense).floor/50).floor+2
    # Multi-targeting attacks
    if pbTargetsMultiple?(attacker)
      damage=(damage*0.75).round
    end
    # Weather
    case @battle.pbWeather
    when PBWeather::SUNNYDAY, PBWeather::HARSHSUN
      if isConst?(type,PBTypes,:FIRE)
        damage=(damage*1.5).round
      elsif isConst?(type,PBTypes,:WATER)
        damage=(damage*0.5).round
      end
    when PBWeather::RAINDANCE, PBWeather::HEAVYRAIN
      if isConst?(type,PBTypes,:FIRE)
        damage=(damage*0.5).round
      elsif isConst?(type,PBTypes,:WATER)
        damage=(damage*1.5).round
      end
    end
    # Critical hits
    if opponent.damagestate.critical
      damage=(USENEWBATTLEMECHANICS) ? (damage*1.5).round : (damage*2.0).round
    end
    # Random variance
    if (options&NOWEIGHTING)==0
      random=85+@battle.pbRandom(16)
      damage=(damage*random/100.0).floor
    end
    # STAB
    if attacker.pbHasType?(type) && (options&IGNOREPKMNTYPES)==0
      if attacker.hasWorkingAbility(:ADAPTABILITY)
        damage=(damage*2).round
      else
        damage=(damage*1.5).round
      end
    end
    # Type effectiveness
    if (options&IGNOREPKMNTYPES)==0
      typemod=pbTypeModMessages(type,attacker,opponent)
      damage=(damage*typemod/8.0).round
      opponent.damagestate.typemod=typemod
      if typemod==0
        opponent.damagestate.calcdamage=0
        opponent.damagestate.critical=false
        return 0
      end
    else
      opponent.damagestate.typemod=8
    end
    # Burn
    if attacker.status==PBStatuses::BURN && pbIsPhysical?(type) &&
       !attacker.hasWorkingAbility(:GUTS) &&
       !(USENEWBATTLEMECHANICS && @function==0x7E) # Facade
      damage=(damage*0.5).round
    end
    # Make sure damage is at least 1
    damage=1 if damage<1
    # Final damage modifiers
    finaldamagemult=0x1000
    if !opponent.damagestate.critical && (options&NOREFLECT)==0 &&
       !attacker.hasWorkingAbility(:INFILTRATOR)
      # Reflect
      if opponent.pbOwnSide.effects[PBEffects::Reflect]>0 && pbIsPhysical?(type)
        if @battle.doublebattle
          finaldamagemult=(finaldamagemult*0.66).round
        else
          finaldamagemult=(finaldamagemult*0.5).round
        end
      end
      # Light Screen
      if opponent.pbOwnSide.effects[PBEffects::LightScreen]>0 && pbIsSpecial?(type)
        if @battle.doublebattle
          finaldamagemult=(finaldamagemult*0.66).round
        else
          finaldamagemult=(finaldamagemult*0.5).round
        end
      end
    end
    if attacker.effects[PBEffects::ParentalBond]==1
      finaldamagemult=(finaldamagemult*0.5).round
    end
    if attacker.hasWorkingAbility(:TINTEDLENS) && opponent.damagestate.typemod<8
      finaldamagemult=(finaldamagemult*2.0).round
    end
    if attacker.hasWorkingAbility(:SNIPER) && opponent.damagestate.critical
      finaldamagemult=(finaldamagemult*1.5).round
    end
    if !attacker.hasMoldBreaker
      if opponent.hasWorkingAbility(:MULTISCALE) && opponent.hp==opponent.totalhp
        finaldamagemult=(finaldamagemult*0.5).round
      end
      if (opponent.hasWorkingAbility(:SOLIDROCK) ||
         opponent.hasWorkingAbility(:FILTER)) &&
         opponent.damagestate.typemod>8
        finaldamagemult=(finaldamagemult*0.75).round
      end
      if opponent.pbPartner.hasWorkingAbility(:FRIENDGUARD)
        finaldamagemult=(finaldamagemult*0.75).round
      end
    end
    if attacker.hasWorkingItem(:METRONOME)
      met=1+0.2*[attacker.effects[PBEffects::Metronome],5].min
      finaldamagemult=(finaldamagemult*met).round
    end
    if attacker.hasWorkingItem(:EXPERTBELT) &&
       opponent.damagestate.typemod>8
      finaldamagemult=(finaldamagemult*1.2).round
    end
    if attacker.hasWorkingItem(:LIFEORB) && (options&SELFCONFUSE)==0
      attacker.effects[PBEffects::LifeOrb]=true
      finaldamagemult=(finaldamagemult*1.3).round
    end
    if opponent.damagestate.typemod>8 && (options&IGNOREPKMNTYPES)==0
      if (opponent.hasWorkingItem(:CHOPLEBERRY) && isConst?(type,PBTypes,:FIGHTING)) ||
         (opponent.hasWorkingItem(:COBABERRY) && isConst?(type,PBTypes,:FLYING)) ||
         (opponent.hasWorkingItem(:KEBIABERRY) && isConst?(type,PBTypes,:POISON)) ||
         (opponent.hasWorkingItem(:SHUCABERRY) && isConst?(type,PBTypes,:GROUND)) ||
         (opponent.hasWorkingItem(:CHARTIBERRY) && isConst?(type,PBTypes,:ROCK)) ||
         (opponent.hasWorkingItem(:TANGABERRY) && isConst?(type,PBTypes,:BUG)) ||
         (opponent.hasWorkingItem(:KASIBBERRY) && isConst?(type,PBTypes,:GHOST)) ||
         (opponent.hasWorkingItem(:BABIRIBERRY) && isConst?(type,PBTypes,:STEEL)) ||
         (opponent.hasWorkingItem(:OCCABERRY) && isConst?(type,PBTypes,:FIRE)) ||
         (opponent.hasWorkingItem(:PASSHOBERRY) && isConst?(type,PBTypes,:WATER)) ||
         (opponent.hasWorkingItem(:RINDOBERRY) && isConst?(type,PBTypes,:GRASS)) ||
         (opponent.hasWorkingItem(:WACANBERRY) && isConst?(type,PBTypes,:ELECTRIC)) ||
         (opponent.hasWorkingItem(:PAYAPABERRY) && isConst?(type,PBTypes,:PSYCHIC)) ||
         (opponent.hasWorkingItem(:YACHEBERRY) && isConst?(type,PBTypes,:ICE)) ||
         (opponent.hasWorkingItem(:HABANBERRY) && isConst?(type,PBTypes,:DRAGON)) ||
         (opponent.hasWorkingItem(:COLBURBERRY) && isConst?(type,PBTypes,:DARK)) ||
         (opponent.hasWorkingItem(:ROSELIBERRY) && isConst?(type,PBTypes,:FAIRY))
        finaldamagemult=(finaldamagemult*0.5).round
        opponent.damagestate.berryweakened=true
        @battle.pbCommonAnimation("UseItem",opponent,nil)
      end
    end
    if opponent.hasWorkingItem(:CHILANBERRY) && isConst?(type,PBTypes,:NORMAL) &&
       (options&IGNOREPKMNTYPES)==0
      finaldamagemult=(finaldamagemult*0.5).round
      opponent.damagestate.berryweakened=true
      @battle.pbCommonAnimation("UseItem",opponent,nil)
    end
    finaldamagemult=pbModifyDamage(finaldamagemult,attacker,opponent)
    damage=(damage*finaldamagemult*1.0/0x1000).round
    opponent.damagestate.calcdamage=damage
    PBDebug.log("Move's damage calculated to be #{damage}")
    return damage
  end

  def pbReduceHPDamage(damage,attacker,opponent)
    endure=false
    if opponent.effects[PBEffects::Substitute]>0 && !ignoresSubstitute?(attacker) &&
       (!attacker || attacker.index!=opponent.index)
      PBDebug.log("[Lingering effect triggered] #{opponent.pbThis}'s Substitute took the damage")
      damage=opponent.effects[PBEffects::Substitute] if damage>opponent.effects[PBEffects::Substitute]
      opponent.effects[PBEffects::Substitute]-=damage
      opponent.damagestate.substitute=true
      @battle.scene.pbDamageAnimation(opponent,0)
      @battle.pbDisplayPaused(_INTL("The substitute took damage for {1}!",opponent.name))
      if opponent.effects[PBEffects::Substitute]<=0
        opponent.effects[PBEffects::Substitute]=0
        @battle.pbDisplayPaused(_INTL("{1}'s substitute faded!",opponent.name))
        PBDebug.log("[End of effect] #{opponent.pbThis}'s Substitute faded")
      end
      opponent.damagestate.hplost=damage
      damage=0
    else
      opponent.damagestate.substitute=false
      if damage>=opponent.hp
        damage=opponent.hp
        if @function==0xE9 # False Swipe
          damage=damage-1
        elsif opponent.effects[PBEffects::Endure]
          damage=damage-1
          opponent.damagestate.endured=true
          PBDebug.log("[Lingering effect triggered] #{opponent.pbThis}'s Endure")
        elsif damage==opponent.totalhp
          if opponent.hasWorkingAbility(:STURDY) && !attacker.hasMoldBreaker
            opponent.damagestate.sturdy=true
            damage=damage-1
            PBDebug.log("[Ability triggered] #{opponent.pbThis}'s Sturdy")
          elsif opponent.hasWorkingItem(:FOCUSSASH) && opponent.hp==opponent.totalhp
            opponent.damagestate.focussash=true
            damage=damage-1
            PBDebug.log("[Item triggered] #{opponent.pbThis}'s Focus Sash")
          elsif opponent.hasWorkingItem(:FOCUSBAND) && @battle.pbRandom(10)==0
            opponent.damagestate.focusband=true
            damage=damage-1
            PBDebug.log("[Item triggered] #{opponent.pbThis}'s Focus Band")
          end
        end
        damage=0 if damage<0
      end
      oldhp=opponent.hp
      opponent.hp-=damage
      effectiveness=0
      if opponent.damagestate.typemod<8
        effectiveness=1   # "Not very effective"
      elsif opponent.damagestate.typemod>8
        effectiveness=2   # "Super effective"
      end
      if opponent.damagestate.typemod!=0
        @battle.scene.pbDamageAnimation(opponent,effectiveness)
      end
      @battle.scene.pbHPChanged(opponent,oldhp)
      opponent.damagestate.hplost=damage
    end
    return damage
  end

################################################################################
# Effects
################################################################################
  def pbEffectMessages(attacker,opponent,ignoretype=false,alltargets=nil)
    if opponent.damagestate.critical
      if alltargets && alltargets.length>1
        @battle.pbDisplay(_INTL("A critical hit on {1}!",opponent.pbThis(true)))
      else
        @battle.pbDisplay(_INTL("A critical hit!"))
      end
    end
    if !pbIsMultiHit && attacker.effects[PBEffects::ParentalBond]==0
      if opponent.damagestate.typemod>8
        if alltargets && alltargets.length>1
          @battle.pbDisplay(_INTL("It's super effective on {1}!",opponent.pbThis(true)))
        else
          @battle.pbDisplay(_INTL("It's super effective!"))
        end
      elsif opponent.damagestate.typemod>=1 && opponent.damagestate.typemod<8
        if alltargets && alltargets.length>1
          @battle.pbDisplay(_INTL("It's not very effective on {1}...",opponent.pbThis(true)))
        else
          @battle.pbDisplay(_INTL("It's not very effective..."))
        end
      end
    end
    if opponent.damagestate.endured
      @battle.pbDisplay(_INTL("{1} endured the hit!",opponent.pbThis))
    elsif opponent.damagestate.sturdy
      @battle.pbDisplay(_INTL("{1} hung on with Sturdy!",opponent.pbThis))
    elsif opponent.damagestate.focussash
      @battle.pbDisplay(_INTL("{1} hung on using its Focus Sash!",opponent.pbThis))
      opponent.pbConsumeItem
    elsif opponent.damagestate.focusband
      @battle.pbDisplay(_INTL("{1} hung on using its Focus Band!",opponent.pbThis))
    end
  end

  def pbEffectFixedDamage(damage,attacker,opponent,hitnum=0,alltargets=nil,showanimation=true)
    type=pbType(@type,attacker,opponent)
    typemod=pbTypeModMessages(type,attacker,opponent)
    opponent.damagestate.critical=false
    opponent.damagestate.typemod=0
    opponent.damagestate.calcdamage=0
    opponent.damagestate.hplost=0
    if typemod!=0
      opponent.damagestate.calcdamage=damage
      opponent.damagestate.typemod=8
      pbShowAnimation(@id,attacker,opponent,hitnum,alltargets,showanimation)
      damage=1 if damage<1 # HP reduced can't be less than 1
      damage=pbReduceHPDamage(damage,attacker,opponent)
      pbEffectMessages(attacker,opponent,alltargets)
      pbOnDamageLost(damage,attacker,opponent)
      return damage
    end
    return 0
  end

  def pbEffect(attacker,opponent,hitnum=0,alltargets=nil,showanimation=true)
    return 0 if !opponent
    damage=pbCalcDamage(attacker,opponent)
    if opponent.damagestate.typemod!=0
      pbShowAnimation(@id,attacker,opponent,hitnum,alltargets,showanimation)
    end
    damage=pbReduceHPDamage(damage,attacker,opponent)
    pbEffectMessages(attacker,opponent)
    pbOnDamageLost(damage,attacker,opponent)
    return damage   # The HP lost by the opponent due to this attack
  end

  def pbEffectAfterHit(attacker,opponent,turneffects)
  end

################################################################################
# Using the move
################################################################################
  def pbOnStartUse(attacker)
    return true
  end

  def pbAddTarget(targets,attacker)
  end

  def pbDisplayUseMessage(attacker)
  # Return values:
  # -1 if the attack should exit as a failure
  # 0 if the attack should proceed with its effect
  # 1 if the attack should exit as a success
  # 2 if Bide is storing energy
    @battle.pbDisplayBrief(_INTL("{1} used\r\n{2}!",attacker.pbThis,name))
    return 0
  end

  def pbShowAnimation(id,attacker,opponent,hitnum=0,alltargets=nil,showanimation=true)
    return if !showanimation
    if attacker.effects[PBEffects::ParentalBond]==1
      @battle.pbCommonAnimation("ParentalBond",attacker,opponent)
      return
    end
    @battle.pbAnimation(id,attacker,opponent,hitnum)
  end

  def pbOnDamageLost(damage,attacker,opponent)
    # Used by Counter/Mirror Coat/Revenge/Focus Punch/Bide
    type=@type
    type=pbType(type,attacker,opponent)
    if opponent.effects[PBEffects::Bide]>0
      opponent.effects[PBEffects::BideDamage]+=damage
      opponent.effects[PBEffects::BideTarget]=attacker.index
    end
    if @function==0x90 # Hidden Power
      type=getConst(PBTypes,:NORMAL) || 0
    end
    if pbIsPhysical?(type)
      opponent.effects[PBEffects::Counter]=damage
      opponent.effects[PBEffects::CounterTarget]=attacker.index
    elsif pbIsSpecial?(type)
      opponent.effects[PBEffects::MirrorCoat]=damage
      opponent.effects[PBEffects::MirrorCoatTarget]=attacker.index
    end
    opponent.lastHPLost=damage # for Revenge/Focus Punch/Metal Burst
    opponent.tookDamage=true if damage>0 # for Assurance
    opponent.lastAttacker.push(attacker.index) # for Revenge/Metal Burst
  end

  def pbMoveFailed(attacker,opponent)
    # Called to determine whether the move failed
    return false
  end
end