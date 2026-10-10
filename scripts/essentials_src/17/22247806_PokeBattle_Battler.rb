class PokeBattle_Battler
  attr_reader :battle
  attr_reader :pokemon
  attr_reader :name
  attr_reader :index
  attr_accessor :pokemonIndex
  attr_reader :totalhp
  attr_reader :fainted
  attr_accessor :lastAttacker
  attr_accessor :turncount
  attr_accessor :effects
  attr_accessor :species
  attr_accessor :type1
  attr_accessor :type2
  attr_accessor :ability
  attr_accessor :gender
  attr_accessor :attack
  attr_writer :defense
  attr_accessor :spatk
  attr_writer :spdef
  attr_accessor :speed
  attr_accessor :stages
  attr_accessor :iv
  attr_accessor :moves
  attr_accessor :participants
  attr_accessor :tookDamage
  attr_accessor :lastHPLost
  attr_accessor :lastMoveUsed
  attr_accessor :lastMoveUsedType
  attr_accessor :lastMoveUsedSketch
  attr_accessor :lastRegularMoveUsed
  attr_accessor :lastRoundMoved
  attr_accessor :movesUsed
  attr_accessor :currentMove
  attr_accessor :damagestate
  attr_accessor :captured

  def inHyperMode?; return false; end
  def isShadow?; return false; end

################################################################################
# Complex accessors
################################################################################
  def defense
    return @battle.field.effects[PBEffects::WonderRoom]>0 ? @spdef : @defense
  end

  def spdef
    return @battle.field.effects[PBEffects::WonderRoom]>0 ? @defense : @spdef
  end

  def nature
    return (@pokemon) ? @pokemon.nature : 0
  end

  def happiness
    return (@pokemon) ? @pokemon.happiness : 0
  end

  def pokerusStage
    return (@pokemon) ? @pokemon.pokerusStage : 0
  end

  attr_reader :form

  def form=(value)
    @form=value
    @pokemon.form=value if @pokemon
  end

  def hasMega?
    return false if @effects[PBEffects::Transform]
    if @pokemon
      return (@pokemon.hasMegaForm? rescue false)
    end
    return false
  end

  def isMega?
    if @pokemon
      return (@pokemon.isMega? rescue false)
    end
    return false
  end

  def hasPrimal?
    return false if @effects[PBEffects::Transform]
    if @pokemon
      return (@pokemon.hasPrimalForm? rescue false)
    end
    return false
  end

  def isPrimal?
    if @pokemon
      return (@pokemon.isPrimal? rescue false)
    end
    return false
  end

  attr_reader :level

  def level=(value)
    @level=value
    @pokemon.level=(value) if @pokemon
  end

  attr_reader :status

  def status=(value)
    if @status==PBStatuses::SLEEP && value==0
      @effects[PBEffects::Truant]=false
    end
    @status=value
    @pokemon.status=value if @pokemon
    if value!=PBStatuses::POISON
      @effects[PBEffects::Toxic]=0
    end
    if value!=PBStatuses::POISON && value!=PBStatuses::SLEEP
      @statusCount=0
      @pokemon.statusCount=0 if @pokemon
    end
  end

  attr_reader :statusCount

  def statusCount=(value)
    @statusCount=value
    @pokemon.statusCount=value if @pokemon
  end

  attr_reader :hp

  def hp=(value)
    @hp=value.to_i
    @pokemon.hp=value.to_i if @pokemon
  end

  attr_reader :item

  def item=(value)
    @item=value
    @pokemon.setItem(value) if @pokemon
  end

  def weight(attacker=nil)
    w=(@pokemon) ? @pokemon.weight : 500
    if !attacker || !attacker.hasMoldBreaker
      w*=2 if self.hasWorkingAbility(:HEAVYMETAL)
      w/=2 if self.hasWorkingAbility(:LIGHTMETAL)
    end
    w/=2 if self.hasWorkingItem(:FLOATSTONE)
    w+=@effects[PBEffects::WeightChange]
    w=w.floor
    w=1 if w<1
    return w
  end

  def name
    if @effects[PBEffects::Illusion]
      return @effects[PBEffects::Illusion].name
    end
    return @name
  end

  def displayGender
    if @effects[PBEffects::Illusion]
      return @effects[PBEffects::Illusion].gender
    end
    return self.gender
  end

  def isShiny?
    if @effects[PBEffects::Illusion]
      return @effects[PBEffects::Illusion].isShiny?
    end
    return @pokemon.isShiny? if @pokemon
    return false
  end

  def owned
    return (@pokemon) ? $Trainer.owned[@pokemon.species] && !@battle.opponent : false
  end

################################################################################
# Creating a battler
################################################################################
  def initialize(btl,index)
    @battle       = btl
    @index        = index
    @hp           = 0
    @totalhp      = 0
    @fainted      = true
    @captured     = false
    @stages       = []
    @effects      = []
    @damagestate  = PokeBattle_DamageState.new
    pbInitBlank
    pbInitEffects(false)
    pbInitPermanentEffects
  end

  def pbInitPokemon(pkmn,pkmnIndex)
    if pkmn.egg?
      raise _INTL("An egg can't be an active Pokémon")
    end
    @name         = pkmn.name
    @species      = pkmn.species
    @level        = pkmn.level
    @hp           = pkmn.hp
    @totalhp      = pkmn.totalhp
    @gender       = pkmn.gender
    @ability      = pkmn.ability
    @item         = pkmn.item
    @type1        = pkmn.type1
    @type2        = pkmn.type2
    @form         = pkmn.form
    @attack       = pkmn.attack
    @defense      = pkmn.defense
    @speed        = pkmn.speed
    @spatk        = pkmn.spatk
    @spdef        = pkmn.spdef
    @status       = pkmn.status
    @statusCount  = pkmn.statusCount
    @pokemon      = pkmn
    @pokemonIndex = pkmnIndex
    @participants = [] # Participants will earn Exp. Points if this battler is defeated
    @moves        = [
       PokeBattle_Move.pbFromPBMove(@battle,pkmn.moves[0]),
       PokeBattle_Move.pbFromPBMove(@battle,pkmn.moves[1]),
       PokeBattle_Move.pbFromPBMove(@battle,pkmn.moves[2]),
       PokeBattle_Move.pbFromPBMove(@battle,pkmn.moves[3])
    ]
    @iv           = []
    @iv[0]        = pkmn.iv[0]
    @iv[1]        = pkmn.iv[1]
    @iv[2]        = pkmn.iv[2]
    @iv[3]        = pkmn.iv[3]
    @iv[4]        = pkmn.iv[4]
    @iv[5]        = pkmn.iv[5]
  end

  def pbInitDummyPokemon(pkmn,pkmnIndex)
    if pkmn.egg?
      raise _INTL("An egg can't be an active Pokémon")
    end
    @name         = pkmn.name
    @species      = pkmn.species
    @level        = pkmn.level
    @hp           = pkmn.hp
    @totalhp      = pkmn.totalhp
    @gender       = pkmn.gender
    @type1        = pkmn.type1
    @type2        = pkmn.type2
    @form         = pkmn.form
    @attack       = pkmn.attack
    @defense      = pkmn.defense
    @speed        = pkmn.speed
    @spatk        = pkmn.spatk
    @spdef        = pkmn.spdef
    @status       = pkmn.status
    @statusCount  = pkmn.statusCount
    @pokemon      = pkmn
    @pokemonIndex = pkmnIndex
    @participants = []
    @iv           = []
    @iv[0]        = pkmn.iv[0]
    @iv[1]        = pkmn.iv[1]
    @iv[2]        = pkmn.iv[2]
    @iv[3]        = pkmn.iv[3]
    @iv[4]        = pkmn.iv[4]
    @iv[5]        = pkmn.iv[5]
  end

  def pbInitBlank
    @name         = ""
    @species      = 0
    @level        = 0
    @hp           = 0
    @totalhp      = 0
    @gender       = 0
    @ability      = 0
    @type1        = 0
    @type2        = 0
    @form         = 0
    @attack       = 0
    @defense      = 0
    @speed        = 0
    @spatk        = 0
    @spdef        = 0
    @status       = 0
    @statusCount  = 0
    @pokemon      = nil
    @pokemonIndex = -1
    @participants = []
    @moves        = [nil,nil,nil,nil]
    @iv           = [0,0,0,0,0,0]
    @item         = 0
    @weight       = nil
  end

  def pbInitPermanentEffects
    # These effects are always retained even if a Pokémon is replaced
    @effects[PBEffects::FutureSight]        = 0
    @effects[PBEffects::FutureSightMove]    = 0
    @effects[PBEffects::FutureSightUser]    = -1
    @effects[PBEffects::FutureSightUserPos] = -1
    @effects[PBEffects::HealingWish]        = false
    @effects[PBEffects::LunarDance]         = false
    @effects[PBEffects::Wish]               = 0
    @effects[PBEffects::WishAmount]         = 0
    @effects[PBEffects::WishMaker]          = -1
  end

  def pbInitEffects(batonpass)
    if !batonpass
      # These effects are retained if Baton Pass is used
      @stages[PBStats::ATTACK]   = 0
      @stages[PBStats::DEFENSE]  = 0
      @stages[PBStats::SPEED]    = 0
      @stages[PBStats::SPATK]    = 0
      @stages[PBStats::SPDEF]    = 0
      @stages[PBStats::EVASION]  = 0
      @stages[PBStats::ACCURACY] = 0
      @lastMoveUsedSketch        = -1
      @effects[PBEffects::AquaRing]    = false
      @effects[PBEffects::Confusion]   = 0
      @effects[PBEffects::Curse]       = false
      @effects[PBEffects::Embargo]     = 0
      @effects[PBEffects::FocusEnergy] = 0
      @effects[PBEffects::GastroAcid]  = false
      @effects[PBEffects::HealBlock]   = 0
      @effects[PBEffects::Ingrain]     = false
      @effects[PBEffects::LeechSeed]   = -1
      @effects[PBEffects::LockOn]      = 0
      @effects[PBEffects::LockOnPos]   = -1
      for i in 0...4
        next if !@battle.battlers[i]
        if @battle.battlers[i].effects[PBEffects::LockOnPos]==@index &&
           @battle.battlers[i].effects[PBEffects::LockOn]>0
          @battle.battlers[i].effects[PBEffects::LockOn]=0
          @battle.battlers[i].effects[PBEffects::LockOnPos]=-1
        end
      end
      @effects[PBEffects::MagnetRise]     = 0
      @effects[PBEffects::PerishSong]     = 0
      @effects[PBEffects::PerishSongUser] = -1
      @effects[PBEffects::PowerTrick]     = false
      @effects[PBEffects::Substitute]     = 0
      @effects[PBEffects::Telekinesis]    = 0
    else
      if @effects[PBEffects::LockOn]>0
        @effects[PBEffects::LockOn]=2
      else
        @effects[PBEffects::LockOn]=0
      end
      if @effects[PBEffects::PowerTrick]
        @attack,@defense=@defense,@attack
      end
    end
    @damagestate.reset
    @fainted          = false
    @lastAttacker     = []
    @lastHPLost       = 0
    @tookDamage       = false
    @lastMoveUsed     = -1
    @lastMoveUsedType = -1
    @lastRoundMoved   = -1
    @movesUsed        = []
    @turncount        = 0
    @effects[PBEffects::Attract]          = -1
    for i in 0...4
      next if !@battle.battlers[i]
      if @battle.battlers[i].effects[PBEffects::Attract]==@index
        @battle.battlers[i].effects[PBEffects::Attract]=-1
      end
    end
    @effects[PBEffects::BatonPass]        = false
    @effects[PBEffects::Bide]             = 0
    @effects[PBEffects::BideDamage]       = 0
    @effects[PBEffects::BideTarget]       = -1
    @effects[PBEffects::Charge]           = 0
    @effects[PBEffects::ChoiceBand]       = -1
    @effects[PBEffects::Counter]          = -1
    @effects[PBEffects::CounterTarget]    = -1
    @effects[PBEffects::DefenseCurl]      = false
    @effects[PBEffects::DestinyBond]      = false
    @effects[PBEffects::Disable]          = 0
    @effects[PBEffects::DisableMove]      = 0
    @effects[PBEffects::Electrify]        = false
    @effects[PBEffects::Encore]           = 0
    @effects[PBEffects::EncoreIndex]      = 0
    @effects[PBEffects::EncoreMove]       = 0
    @effects[PBEffects::Endure]           = false
    @effects[PBEffects::FirstPledge]      = 0
    @effects[PBEffects::FlashFire]        = false
    @effects[PBEffects::Flinch]           = false
    @effects[PBEffects::FollowMe]         = 0
    @effects[PBEffects::Foresight]        = false
    @effects[PBEffects::FuryCutter]       = 0
    @effects[PBEffects::Grudge]           = false
    @effects[PBEffects::HelpingHand]      = false
    @effects[PBEffects::HyperBeam]        = 0
    @effects[PBEffects::Illusion]         = nil
    if self.hasWorkingAbility(:ILLUSION)
      lastpoke=@battle.pbGetLastPokeInTeam(@index)
      if lastpoke!=@pokemonIndex
        @effects[PBEffects::Illusion]     = @battle.pbParty(@index)[lastpoke]
      end
    end
    @effects[PBEffects::Imprison]         = false
    @effects[PBEffects::KingsShield]      = false
    @effects[PBEffects::LifeOrb]          = false
    @effects[PBEffects::MagicCoat]        = false
    @effects[PBEffects::MeanLook]         = -1
    for i in 0...4
      next if !@battle.battlers[i]
      if @battle.battlers[i].effects[PBEffects::MeanLook]==@index
        @battle.battlers[i].effects[PBEffects::MeanLook]=-1
      end
    end
    @effects[PBEffects::MeFirst]          = false
    @effects[PBEffects::Metronome]        = 0
    @effects[PBEffects::MicleBerry]       = false
    @effects[PBEffects::Minimize]         = false
    @effects[PBEffects::MiracleEye]       = false
    @effects[PBEffects::MirrorCoat]       = -1
    @effects[PBEffects::MirrorCoatTarget] = -1
    @effects[PBEffects::MoveNext]         = false
    @effects[PBEffects::MudSport]         = false
    @effects[PBEffects::MultiTurn]        = 0
    @effects[PBEffects::MultiTurnAttack]  = 0
    @effects[PBEffects::MultiTurnUser]    = -1
    for i in 0...4
      next if !@battle.battlers[i]
      if @battle.battlers[i].effects[PBEffects::MultiTurnUser]==@index
        @battle.battlers[i].effects[PBEffects::MultiTurn]=0
        @battle.battlers[i].effects[PBEffects::MultiTurnUser]=-1
      end
    end
    @effects[PBEffects::Nightmare]        = false
    @effects[PBEffects::Outrage]          = 0
    @effects[PBEffects::ParentalBond]     = 0
    @effects[PBEffects::PickupItem]       = 0
    @effects[PBEffects::PickupUse]        = 0
    @effects[PBEffects::Pinch]            = false
    @effects[PBEffects::Powder]           = false
    @effects[PBEffects::Protect]          = false
    @effects[PBEffects::ProtectNegation]  = false
    @effects[PBEffects::ProtectRate]      = 1
    @effects[PBEffects::Pursuit]          = false
    @effects[PBEffects::Quash]            = false
    @effects[PBEffects::Rage]             = false
    @effects[PBEffects::Revenge]          = 0
    @effects[PBEffects::Roar]             = false
    @effects[PBEffects::Rollout]          = 0
    @effects[PBEffects::Roost]            = false
    @effects[PBEffects::SkipTurn]         = false
    @effects[PBEffects::SkyDrop]          = false
    @effects[PBEffects::SmackDown]        = false
    @effects[PBEffects::Snatch]           = false
    @effects[PBEffects::SpikyShield]      = false
    @effects[PBEffects::Stockpile]        = 0
    @effects[PBEffects::StockpileDef]     = 0
    @effects[PBEffects::StockpileSpDef]   = 0
    @effects[PBEffects::Taunt]            = 0
    @effects[PBEffects::Torment]          = false
    @effects[PBEffects::Toxic]            = 0
    @effects[PBEffects::Transform]        = false
    @effects[PBEffects::Truant]           = false
    @effects[PBEffects::TwoTurnAttack]    = 0
    @effects[PBEffects::Type3]            = -1
    @effects[PBEffects::Unburden]         = false
    @effects[PBEffects::Uproar]           = 0
    @effects[PBEffects::Uturn]            = false
    @effects[PBEffects::WaterSport]       = false
    @effects[PBEffects::WeightChange]     = 0
    @effects[PBEffects::Yawn]             = 0
  end

  def pbUpdate(fullchange=false)
    if @pokemon
      @pokemon.calcStats
      @level     = @pokemon.level
      @hp        = @pokemon.hp
      @totalhp   = @pokemon.totalhp
      if !@effects[PBEffects::Transform]
        @attack    = @pokemon.attack
        @defense   = @pokemon.defense
        @speed     = @pokemon.speed
        @spatk     = @pokemon.spatk
        @spdef     = @pokemon.spdef
        if fullchange
          @ability = @pokemon.ability
          @type1   = @pokemon.type1
          @type2   = @pokemon.type2
        end
      end
    end
  end

  def pbInitialize(pkmn,index,batonpass)
    # Cure status of previous Pokemon with Natural Cure
    if self.hasWorkingAbility(:NATURALCURE)
      self.status=0
    end
    if self.hasWorkingAbility(:REGENERATOR)
      self.pbRecoverHP((totalhp/3).floor)
    end
    pbInitPokemon(pkmn,index)
    pbInitEffects(batonpass)
  end

# Used only to erase the battler of a Shadow Pokémon that has been snagged.
  def pbReset
    @pokemon                = nil
    @pokemonIndex           = -1
    self.hp                 = 0
    pbInitEffects(false)
    # reset status
    self.status             = 0
    self.statusCount        = 0
    @fainted                = true
    # reset choice
    @battle.choices[@index] = [0,0,nil,-1]
    return true
  end

# Update Pokémon who will gain EXP if this battler is defeated
  def pbUpdateParticipants
    return if fainted? # can't update if already fainted
    if @battle.pbIsOpposing?(@index)
      found1=false
      found2=false
      for i in @participants
        found1=true if i==pbOpposing1.pokemonIndex
        found2=true if i==pbOpposing2.pokemonIndex
      end
      if !found1 && !pbOpposing1.fainted?
        @participants[@participants.length]=pbOpposing1.pokemonIndex
      end
      if !found2 && !pbOpposing2.fainted?
        @participants[@participants.length]=pbOpposing2.pokemonIndex
      end
    end
  end

################################################################################
# About this battler
################################################################################
  def fainted?
    return @hp<=0
  end

  alias isFainted? fainted?

  def pbThis(lowercase=false)
    if @battle.pbIsOpposing?(@index)
      if @battle.opponent
        return lowercase ? _INTL("the opposing {1}",self.name) : _INTL("The opposing {1}",self.name)
      else
        return lowercase ? _INTL("the wild {1}",self.name) : _INTL("The wild {1}",self.name)
      end
    elsif @battle.pbOwnedByPlayer?(@index)
      return self.name
    else
      return lowercase ? _INTL("the ally {1}",self.name) : _INTL("The ally {1}",self.name)
    end
  end

  def pbHasType?(type)
    if type.is_a?(Symbol) || type.is_a?(String)
      type = getConst(PBTypes,type)
    end
    return false if type==nil || type<0
    ret = (self.type1==type || self.type2==type)
    ret |= (@effects[PBEffects::Type3]==type) if @effects[PBEffects::Type3]>=0
    return ret
  end
  
  def pbHasMove?(id)
    if id.is_a?(String) || id.is_a?(Symbol)
      id = getID(PBMoves,id)
    end
    return false if !id || id==0
    for i in @moves
      return true if i.id==id
    end
    return false
  end

  def pbHasMoveType?(type)
    if type.is_a?(String) || type.is_a?(Symbol)
      type = getConst(PBTypes,type)
    end
    return false if type==nil || type<0
    for i in @moves
      return true if i.type==type
    end
    return false
  end

  def pbHasMoveFunction?(code)
    return false if !code
    for i in @moves
      return true if i.function==code
    end
    return false
  end

  def hasMovedThisRound?
    return false if !@lastRoundMoved
    return @lastRoundMoved==@battle.turncount
  end

  def hasMoldBreaker
    return true if hasWorkingAbility(:MOLDBREAKER) ||
                   hasWorkingAbility(:TERAVOLT) ||
                   hasWorkingAbility(:TURBOBLAZE)
    return false
  end

  def hasWorkingAbility(ability,ignorefainted=false)
    return false if fainted? && !ignorefainted
    return false if @effects[PBEffects::GastroAcid]
    return isConst?(@ability,PBAbilities,ability)
  end

  def hasWorkingItem(item,ignorefainted=false)
    return false if fainted? && !ignorefainted
    return false if @effects[PBEffects::Embargo]>0
    return false if @battle.field.effects[PBEffects::MagicRoom]>0
    return false if self.hasWorkingAbility(:KLUTZ,ignorefainted)
    return isConst?(@item,PBItems,item)
  end

  def hasWorkingBerry(ignorefainted=false)
    return false if fainted? && !ignorefainted
    return false if @effects[PBEffects::Embargo]>0
    return false if @battle.field.effects[PBEffects::MagicRoom]>0
    return false if self.hasWorkingAbility(:KLUTZ,ignorefainted)
    return pbIsBerry?(@item)
  end

  def isAirborne?(ignoreability=false)
    return false if self.hasWorkingItem(:IRONBALL)
    return false if @effects[PBEffects::Ingrain]
    return false if @effects[PBEffects::SmackDown]
    return false if @battle.field.effects[PBEffects::Gravity]>0
    return true if self.pbHasType?(:FLYING) && !@effects[PBEffects::Roost]
    return true if self.hasWorkingAbility(:LEVITATE) && !ignoreability
    return true if self.hasWorkingItem(:AIRBALLOON)
    return true if @effects[PBEffects::MagnetRise]>0
    return true if @effects[PBEffects::Telekinesis]>0
    return false
  end

  def pbSpeed
    stagemul=[10,10,10,10,10,10,10,15,20,25,30,35,40]
    stagediv=[40,35,30,25,20,15,10,10,10,10,10,10,10]
    speed=@speed
    stage=@stages[PBStats::SPEED]+6
    speed=(speed*stagemul[stage]/stagediv[stage]).floor
    speedmult=0x1000
    case @battle.pbWeather
    when PBWeather::RAINDANCE, PBWeather::HEAVYRAIN
      speedmult=speedmult*2 if self.hasWorkingAbility(:SWIFTSWIM)
    when PBWeather::SUNNYDAY, PBWeather::HARSHSUN
      speedmult=speedmult*2 if self.hasWorkingAbility(:CHLOROPHYLL)
    when PBWeather::SANDSTORM
      speedmult=speedmult*2 if self.hasWorkingAbility(:SANDRUSH)
    end
    if self.hasWorkingAbility(:QUICKFEET) && self.status>0
      speedmult=(speedmult*1.5).round
    end
    if self.hasWorkingAbility(:UNBURDEN) && @effects[PBEffects::Unburden] &&
       self.item==0
      speedmult=speedmult*2
    end
    if self.hasWorkingAbility(:SLOWSTART) && self.turncount<=5
      speedmult=(speedmult/2).round
    end
    if self.hasWorkingItem(:MACHOBRACE) ||
       self.hasWorkingItem(:POWERWEIGHT) ||
       self.hasWorkingItem(:POWERBRACER) ||
       self.hasWorkingItem(:POWERBELT) ||
       self.hasWorkingItem(:POWERANKLET) ||
       self.hasWorkingItem(:POWERLENS) ||
       self.hasWorkingItem(:POWERBAND)
      speedmult=(speedmult/2).round
    end
    if self.hasWorkingItem(:CHOICESCARF)
      speedmult=(speedmult*1.5).round
    end
    if isConst?(self.item,PBItems,:IRONBALL)
      speedmult=(speedmult/2).round
    end
    if self.hasWorkingItem(:QUICKPOWDER) && isConst?(self.species,PBSpecies,:DITTO) &&
       !@effects[PBEffects::Transform]
      speedmult=speedmult*2
    end
    if self.pbOwnSide.effects[PBEffects::Tailwind]>0
      speedmult=speedmult*2
    end
    if self.pbOwnSide.effects[PBEffects::Swamp]>0
      speedmult=(speedmult/2).round
    end
    if self.status==PBStatuses::PARALYSIS && !self.hasWorkingAbility(:QUICKFEET)
      speedmult=(speedmult/4).round
    end
    if @battle.internalbattle && @battle.pbOwnedByPlayer?(@index) &&
       @battle.pbPlayer.numbadges>=BADGESBOOSTSPEED
      speedmult=(speedmult*1.1).round
    end
    speed=(speed*speedmult*1.0/0x1000).round
    return [speed,1].max
  end

################################################################################
# Change HP
################################################################################
  def pbReduceHP(amt,anim=false,registerDamage=true)
    if amt>=self.hp
      amt=self.hp
    elsif amt<1 && !fainted?
      amt=1
    end
    oldhp=self.hp
    self.hp-=amt
    raise _INTL("HP less than 0") if self.hp<0
    raise _INTL("HP greater than total HP") if self.hp>@totalhp
    @battle.scene.pbHPChanged(self,oldhp,anim) if amt>0
    @tookDamage=true if amt>0 && registerDamage
    return amt
  end

  def pbRecoverHP(amt,anim=false)
    if self.hp+amt>@totalhp
      amt=@totalhp-self.hp
    elsif amt<1 && self.hp!=@totalhp
      amt=1
    end
    oldhp=self.hp
    self.hp+=amt
    raise _INTL("HP less than 0") if self.hp<0
    raise _INTL("HP greater than total HP") if self.hp>@totalhp
    @battle.scene.pbHPChanged(self,oldhp,anim) if amt>0
    return amt
  end

  def pbFaint(showMessage=true)
    unless fainted?
      PBDebug.log("!!!***Can't faint with HP greater than 0")
      return true
    end
    if @fainted
#      PBDebug.log("!!!***Can't faint if already fainted")
      return true
    end
    @battle.scene.pbFainted(self)
    pbInitEffects(false)
    # Reset status
    self.status=0
    self.statusCount=0
    if @pokemon && @battle.internalbattle
      @pokemon.changeHappiness("faint")
    end
    @pokemon.makeUnmega if self.isMega?
    @pokemon.makeUnprimal if self.isPrimal?
    @fainted=true
    # reset choice
    @battle.choices[@index]=[0,0,nil,-1]
    pbOwnSide.effects[PBEffects::LastRoundFainted]=@battle.turncount
    @battle.pbDisplayPaused(_INTL("{1} fainted!",pbThis)) if showMessage
    PBDebug.log("[Pokémon fainted] #{pbThis}")
    return true
  end
################################################################################
# Find other battlers/sides in relation to this battler
################################################################################
# Returns the data structure for this battler's side
  def pbOwnSide
    return @battle.sides[@index&1] # Player: 0 and 2; Foe: 1 and 3
  end

# Returns the data structure for the opposing Pokémon's side
  def pbOpposingSide
    return @battle.sides[(@index&1)^1] # Player: 1 and 3; Foe: 0 and 2
  end

# Returns whether the position belongs to the opposing Pokémon's side
  def pbIsOpposing?(i)
    return (@index&1)!=(i&1)
  end

# Returns the battler's partner
  def pbPartner
    return @battle.battlers[(@index&1)|((@index&2)^2)]
  end

# Returns the battler's first opposing Pokémon
  def pbOpposing1
    return @battle.battlers[((@index&1)^1)]
  end

# Returns the battler's second opposing Pokémon
  def pbOpposing2
    return @battle.battlers[((@index&1)^1)+2]
  end

  def pbOppositeOpposing
    return @battle.battlers[(@index^1)]
  end

  def pbOppositeOpposing2
    return @battle.battlers[(@index^1)|((@index&2)^2)]
  end

  def pbNonActivePokemonCount()
    count=0
    party=@battle.pbParty(self.index)
    for i in 0...party.length
      if (fainted? || i!=self.pokemonIndex) &&
         (pbPartner.fainted? || i!=self.pbPartner.pokemonIndex) &&
         party[i] && !party[i].egg? && party[i].hp>0
        count+=1
      end
    end
    return count
  end

################################################################################
# Forms
################################################################################
  def pbCheckForm
    return if @effects[PBEffects::Transform]
    return if fainted?
    transformed=false
    # Forecast
    if isConst?(self.species,PBSpecies,:CASTFORM)
      if self.hasWorkingAbility(:FORECAST)
        case @battle.pbWeather
        when PBWeather::SUNNYDAY, PBWeather::HARSHSUN
          if self.form!=1
            self.form=1; transformed=true
          end
        when PBWeather::RAINDANCE, PBWeather::HEAVYRAIN
          if self.form!=2
            self.form=2; transformed=true
          end
        when PBWeather::HAIL
          if self.form!=3
            self.form=3; transformed=true
          end
        else
          if self.form!=0
            self.form=0; transformed=true
          end
        end
      else
        if self.form!=0
          self.form=0; transformed=true
        end
      end
    end
    # Cherrim
    if isConst?(self.species,PBSpecies,:CHERRIM)
      if self.hasWorkingAbility(:FLOWERGIFT) &&
         (@battle.pbWeather==PBWeather::SUNNYDAY ||
         @battle.pbWeather==PBWeather::HARSHSUN)
        if self.form!=1
          self.form=1; transformed=true
        end
      else
        if self.form!=0
          self.form=0; transformed=true
        end
      end
    end
    # Shaymin
    if isConst?(self.species,PBSpecies,:SHAYMIN)
      if self.form!=@pokemon.form
        self.form=@pokemon.form
        transformed=true
      end
    end
    # Giratina
    if isConst?(self.species,PBSpecies,:GIRATINA)
      if self.form!=@pokemon.form
        self.form=@pokemon.form
        transformed=true
      end
    end
    # Arceus
    if isConst?(self.ability,PBAbilities,:MULTITYPE) &&
       isConst?(self.species,PBSpecies,:ARCEUS)
      if self.form!=@pokemon.form
        self.form=@pokemon.form
        transformed=true
      end
    end
    # Zen Mode
    if isConst?(self.species,PBSpecies,:DARMANITAN)
      if self.hasWorkingAbility(:ZENMODE) && @hp<=((@totalhp/2).floor)
        if self.form!=1
          self.form=1; transformed=true
        end
      else
        if self.form!=0
          self.form=0; transformed=true
        end
      end
    end
    # Keldeo
    if isConst?(self.species,PBSpecies,:KELDEO)
      if self.form!=@pokemon.form
        self.form=@pokemon.form
        transformed=true
      end
    end
    # Genesect
    if isConst?(self.species,PBSpecies,:GENESECT)
      if self.form!=@pokemon.form
        self.form=@pokemon.form
        transformed=true
      end
    end
    if transformed
      pbUpdate(true)
      @battle.scene.pbChangePokemon(self,@pokemon)
      @battle.pbDisplay(_INTL("{1} transformed!",pbThis))
      PBDebug.log("[Form changed] #{pbThis} changed to form #{self.form}")
    end
  end

  def pbResetForm
    if !@effects[PBEffects::Transform]
      if isConst?(self.species,PBSpecies,:CASTFORM) ||
         isConst?(self.species,PBSpecies,:CHERRIM) ||
         isConst?(self.species,PBSpecies,:DARMANITAN) ||
         isConst?(self.species,PBSpecies,:MELOETTA) ||
         isConst?(self.species,PBSpecies,:AEGISLASH) ||
         isConst?(self.species,PBSpecies,:XERNEAS)
        self.form=0
      end
    end
    pbUpdate(true)
  end

################################################################################
# Ability effects
################################################################################
  def pbAbilitiesOnSwitchIn(onactive)
    return if fainted?
    if onactive
      @battle.pbPrimalReversion(self.index)
    end
    # Weather
    if onactive
      if self.hasWorkingAbility(:PRIMORDIALSEA) && @battle.weather!=PBWeather::HEAVYRAIN
        @battle.weather=PBWeather::HEAVYRAIN
        @battle.weatherduration=-1
        @battle.pbCommonAnimation("HeavyRain",nil,nil)
        @battle.pbDisplay(_INTL("{1}'s {2} made a heavy rain begin to fall!",pbThis,PBAbilities.getName(self.ability)))
        PBDebug.log("[Ability triggered] #{pbThis}'s Primordial Sea made it rain heavily")
      end
      if self.hasWorkingAbility(:DESOLATELAND) && @battle.weather!=PBWeather::HARSHSUN
        @battle.weather=PBWeather::HARSHSUN
        @battle.weatherduration=-1
        @battle.pbCommonAnimation("HarshSun",nil,nil)
        @battle.pbDisplay(_INTL("{1}'s {2} turned the sunlight extremely harsh!",pbThis,PBAbilities.getName(self.ability)))
        PBDebug.log("[Ability triggered] #{pbThis}'s Desolate Land made the sun shine harshly")
      end
      if self.hasWorkingAbility(:DELTASTREAM) && @battle.weather!=PBWeather::STRONGWINDS
        @battle.weather=PBWeather::STRONGWINDS
        @battle.weatherduration=-1
        @battle.pbCommonAnimation("StrongWinds",nil,nil)
        @battle.pbDisplay(_INTL("{1}'s {2} caused a mysterious air current that protects Flying-type Pokémon!",pbThis,PBAbilities.getName(self.ability)))
        PBDebug.log("[Ability triggered] #{pbThis}'s Delta Stream made an air current blow")
      end
      if @battle.weather!=PBWeather::HEAVYRAIN &&
         @battle.weather!=PBWeather::HARSHSUN &&
         @battle.weather!=PBWeather::STRONGWINDS
        if self.hasWorkingAbility(:DRIZZLE) && (@battle.weather!=PBWeather::RAINDANCE || @battle.weatherduration!=-1)
          @battle.weather=PBWeather::RAINDANCE
          if USENEWBATTLEMECHANICS
            @battle.weatherduration=5
            @battle.weatherduration=8 if hasWorkingItem(:DAMPROCK)
          else
            @battle.weatherduration=-1
          end
          @battle.pbCommonAnimation("Rain",nil,nil)
          @battle.pbDisplay(_INTL("{1}'s {2} made it rain!",pbThis,PBAbilities.getName(self.ability)))
          PBDebug.log("[Ability triggered] #{pbThis}'s Drizzle made it rain")
        end
        if self.hasWorkingAbility(:DROUGHT) && (@battle.weather!=PBWeather::SUNNYDAY || @battle.weatherduration!=-1)
          @battle.weather=PBWeather::SUNNYDAY
          if USENEWBATTLEMECHANICS
            @battle.weatherduration=5
            @battle.weatherduration=8 if hasWorkingItem(:HEATROCK)
          else
            @battle.weatherduration=-1
          end
          @battle.pbCommonAnimation("Sunny",nil,nil)
          @battle.pbDisplay(_INTL("{1}'s {2} intensified the sun's rays!",pbThis,PBAbilities.getName(self.ability)))
          PBDebug.log("[Ability triggered] #{pbThis}'s Drought made it sunny")
        end
        if self.hasWorkingAbility(:SANDSTREAM) && (@battle.weather!=PBWeather::SANDSTORM || @battle.weatherduration!=-1)
          @battle.weather=PBWeather::SANDSTORM
          if USENEWBATTLEMECHANICS
            @battle.weatherduration=5
            @battle.weatherduration=8 if hasWorkingItem(:SMOOTHROCK)
          else
            @battle.weatherduration=-1
          end
          @battle.pbCommonAnimation("Sandstorm",nil,nil)
          @battle.pbDisplay(_INTL("{1}'s {2} whipped up a sandstorm!",pbThis,PBAbilities.getName(self.ability)))
          PBDebug.log("[Ability triggered] #{pbThis}'s Sand Stream made it sandstorm")
        end
        if self.hasWorkingAbility(:SNOWWARNING) && (@battle.weather!=PBWeather::HAIL || @battle.weatherduration!=-1)
          @battle.weather=PBWeather::HAIL
          if USENEWBATTLEMECHANICS
            @battle.weatherduration=5
            @battle.weatherduration=8 if hasWorkingItem(:ICYROCK)
          else
            @battle.weatherduration=-1
          end
          @battle.pbCommonAnimation("Hail",nil,nil)
          @battle.pbDisplay(_INTL("{1}'s {2} made it hail!",pbThis,PBAbilities.getName(self.ability)))
          PBDebug.log("[Ability triggered] #{pbThis}'s Snow Warning made it hail")
        end
      end
      if self.hasWorkingAbility(:AIRLOCK) ||
         self.hasWorkingAbility(:CLOUDNINE)
        @battle.pbDisplay(_INTL("{1} has {2}!",pbThis,PBAbilities.getName(self.ability)))
        @battle.pbDisplay(_INTL("The effects of the weather disappeared."))
      end
    end
    @battle.pbPrimordialWeather
    # Trace
    if self.hasWorkingAbility(:TRACE)
      choices=[]
      for i in 0...4
        foe=@battle.battlers[i]
        if pbIsOpposing?(i) && !foe.fainted?
          abil=foe.ability
          if abil>0 &&
             !isConst?(abil,PBAbilities,:TRACE) &&
             !isConst?(abil,PBAbilities,:MULTITYPE) &&
             !isConst?(abil,PBAbilities,:ILLUSION) &&
             !isConst?(abil,PBAbilities,:FLOWERGIFT) &&
             !isConst?(abil,PBAbilities,:IMPOSTER) &&
             !isConst?(abil,PBAbilities,:STANCECHANGE)
            choices.push(i)
          end
        end
      end
      if choices.length>0
        choice=choices[@battle.pbRandom(choices.length)]
        battlername=@battle.battlers[choice].pbThis(true)
        battlerability=@battle.battlers[choice].ability
        @ability=battlerability
        abilityname=PBAbilities.getName(battlerability)
        @battle.pbDisplay(_INTL("{1} traced {2}'s {3}!",pbThis,battlername,abilityname))
        PBDebug.log("[Ability triggered] #{pbThis}'s Trace turned into #{abilityname} from #{battlername}")
      end
    end
    # Intimidate
    if self.hasWorkingAbility(:INTIMIDATE) && onactive
      PBDebug.log("[Ability triggered] #{pbThis}'s Intimidate")
      for i in 0...4
        if pbIsOpposing?(i) && !@battle.battlers[i].fainted?
          @battle.battlers[i].pbReduceAttackStatIntimidate(self)
        end
      end
    end
    # Download
    if self.hasWorkingAbility(:DOWNLOAD) && onactive
      odef=ospdef=0
      if pbOpposing1 && !pbOpposing1.fainted?
        odef+=pbOpposing1.defense
        ospdef+=pbOpposing1.spdef
      end
      if pbOpposing2 && !pbOpposing2.fainted?
        odef+=pbOpposing2.defense
        ospdef+=pbOpposing1.spdef
      end
      if ospdef>odef
        if pbIncreaseStatWithCause(PBStats::ATTACK,1,self,PBAbilities.getName(ability))
          PBDebug.log("[Ability triggered] #{pbThis}'s Download (raising Attack)")
        end
      else
        if pbIncreaseStatWithCause(PBStats::SPATK,1,self,PBAbilities.getName(ability))
          PBDebug.log("[Ability triggered] #{pbThis}'s Download (raising Special Attack)")
        end
      end
    end
    # Frisk
    if self.hasWorkingAbility(:FRISK) && @battle.pbOwnedByPlayer?(@index) && onactive
      foes=[]
      foes.push(pbOpposing1) if pbOpposing1.item>0 && !pbOpposing1.fainted?
      foes.push(pbOpposing2) if pbOpposing2.item>0 && !pbOpposing2.fainted?
      if USENEWBATTLEMECHANICS
        PBDebug.log("[Ability triggered] #{pbThis}'s Frisk") if foes.length>0
        for i in foes
          itemname=PBItems.getName(i.item)
          @battle.pbDisplay(_INTL("{1} frisked {2} and found its {3}!",pbThis,i.pbThis(true),itemname))
        end
      elsif foes.length>0
        PBDebug.log("[Ability triggered] #{pbThis}'s Frisk")
        foe=foes[@battle.pbRandom(foes.length)]
        itemname=PBItems.getName(foe.item)
        @battle.pbDisplay(_INTL("{1} frisked the foe and found one {2}!",pbThis,itemname))
      end
    end
    # Anticipation
    if self.hasWorkingAbility(:ANTICIPATION) && @battle.pbOwnedByPlayer?(@index) && onactive
      PBDebug.log("[Ability triggered] #{pbThis} has Anticipation")
      found=false
      for foe in [pbOpposing1,pbOpposing2]
        next if foe.fainted?
        for j in foe.moves
          movedata=PBMoveData.new(j.id)
          eff=PBTypes.getCombinedEffectiveness(movedata.type,type1,type2,@effects[PBEffects::Type3])
          if (movedata.basedamage>0 && eff>8) ||
             (movedata.function==0x70 && eff>0) # OHKO
            found=true
            break
          end
        end
        break if found
      end
      @battle.pbDisplay(_INTL("{1} shuddered with anticipation!",pbThis)) if found
    end
    # Forewarn
    if self.hasWorkingAbility(:FOREWARN) && @battle.pbOwnedByPlayer?(@index) && onactive
      PBDebug.log("[Ability triggered] #{pbThis} has Forewarn")
      highpower=0
      fwmoves=[]
      for foe in [pbOpposing1,pbOpposing2]
        next if foe.fainted?
        for j in foe.moves
          movedata=PBMoveData.new(j.id)
          power=movedata.basedamage
          power=160 if movedata.function==0x70    # OHKO
          power=150 if movedata.function==0x8B    # Eruption
          power=120 if movedata.function==0x71 || # Counter
                       movedata.function==0x72 || # Mirror Coat
                       movedata.function==0x73 || # Metal Burst
          power=80 if movedata.function==0x6A ||  # SonicBoom
                      movedata.function==0x6B ||  # Dragon Rage
                      movedata.function==0x6D ||  # Night Shade
                      movedata.function==0x6E ||  # Endeavor
                      movedata.function==0x6F ||  # Psywave
                      movedata.function==0x89 ||  # Return
                      movedata.function==0x8A ||  # Frustration
                      movedata.function==0x8C ||  # Crush Grip
                      movedata.function==0x8D ||  # Gyro Ball
                      movedata.function==0x90 ||  # Hidden Power
                      movedata.function==0x96 ||  # Natural Gift
                      movedata.function==0x97 ||  # Trump Card
                      movedata.function==0x98 ||  # Flail
                      movedata.function==0x9A     # Grass Knot
          if power>highpower
            fwmoves=[j.id]; highpower=power
          elsif power==highpower
            fwmoves.push(j.id)
          end
        end
      end
      if fwmoves.length>0
        fwmove=fwmoves[@battle.pbRandom(fwmoves.length)]
        movename=PBMoves.getName(fwmove)
        @battle.pbDisplay(_INTL("{1}'s Forewarn alerted it to {2}!",pbThis,movename))
      end
    end
    # Pressure message
    if self.hasWorkingAbility(:PRESSURE) && onactive
      @battle.pbDisplay(_INTL("{1} is exerting its pressure!",pbThis))
    end
    # Mold Breaker message
    if self.hasWorkingAbility(:MOLDBREAKER) && onactive
      @battle.pbDisplay(_INTL("{1} breaks the mold!",pbThis))
    end
    # Turboblaze message
    if self.hasWorkingAbility(:TURBOBLAZE) && onactive
      @battle.pbDisplay(_INTL("{1} is radiating a blazing aura!",pbThis))
    end
    # Teravolt message
    if self.hasWorkingAbility(:TERAVOLT) && onactive
      @battle.pbDisplay(_INTL("{1} is radiating a bursting aura!",pbThis))
    end
    # Dark Aura message
    if self.hasWorkingAbility(:DARKAURA) && onactive
      @battle.pbDisplay(_INTL("{1} is radiating a dark aura!",pbThis))
    end
    # Fairy Aura message
    if self.hasWorkingAbility(:FAIRYAURA) && onactive
      @battle.pbDisplay(_INTL("{1} is radiating a fairy aura!",pbThis))
    end
    # Aura Break message
    if self.hasWorkingAbility(:AURABREAK) && onactive
      @battle.pbDisplay(_INTL("{1} reversed all other Pokémon's auras!",pbThis))
    end
    # Slow Start message
    if self.hasWorkingAbility(:SLOWSTART) && onactive
      @battle.pbDisplay(_INTL("{1} can't get it going because of its {2}!",
         pbThis,PBAbilities.getName(self.ability)))
    end
    # Imposter
    if self.hasWorkingAbility(:IMPOSTER) && !@effects[PBEffects::Transform] && onactive
      choice=pbOppositeOpposing
      blacklist=[
         0xC9,    # Fly
         0xCA,    # Dig
         0xCB,    # Dive
         0xCC,    # Bounce
         0xCD,    # Shadow Force
         0xCE,    # Sky Drop
         0x14D    # Phantom Force
      ]
      if choice.effects[PBEffects::Transform] ||
         choice.effects[PBEffects::Illusion] ||
         choice.effects[PBEffects::Substitute]>0 ||
         choice.effects[PBEffects::SkyDrop] ||
         blacklist.include?(PBMoveData.new(choice.effects[PBEffects::TwoTurnAttack]).function)
        PBDebug.log("[Ability triggered] #{pbThis}'s Imposter couldn't transform")
      else
        PBDebug.log("[Ability triggered] #{pbThis}'s Imposter")
        @battle.pbAnimation(getConst(PBMoves,:TRANSFORM),self,choice)
        @effects[PBEffects::Transform]=true
        @type1=choice.type1
        @type2=choice.type2
        @effects[PBEffects::Type3]=-1
        @ability=choice.ability
        @attack=choice.attack
        @defense=choice.defense
        @speed=choice.speed
        @spatk=choice.spatk
        @spdef=choice.spdef
        for i in [PBStats::ATTACK,PBStats::DEFENSE,PBStats::SPEED,
                  PBStats::SPATK,PBStats::SPDEF,PBStats::ACCURACY,PBStats::EVASION]
          @stages[i]=choice.stages[i]
        end
        for i in 0...4
          @moves[i]=PokeBattle_Move.pbFromPBMove(@battle,PBMove.new(choice.moves[i].id))
          @moves[i].pp=5
          @moves[i].totalpp=5
        end
        @effects[PBEffects::Disable]=0
        @effects[PBEffects::DisableMove]=0
        @battle.pbDisplay(_INTL("{1} transformed into {2}!",pbThis,choice.pbThis(true)))
        PBDebug.log("[Pokémon transformed] #{pbThis} transformed into #{choice.pbThis(true)}")
      end
    end
    # Air Balloon message
    if self.hasWorkingItem(:AIRBALLOON) && onactive
      @battle.pbDisplay(_INTL("{1} floats in the air with its {2}!",pbThis,PBItems.getName(self.item)))
    end
  end

  def pbEffectsOnDealingDamage(move,user,target,damage)
    movetype=move.pbType(move.type,user,target)
    if damage>0 && move.isContactMove?
      if !target.damagestate.substitute
        if target.hasWorkingItem(:STICKYBARB,true) && user.item==0 && !user.fainted?
          user.item=target.item
          target.item=0
          target.effects[PBEffects::Unburden]=true
          if !@battle.opponent && !@battle.pbIsOpposing?(user.index)
            if user.pokemon.itemInitial==0 && target.pokemon.itemInitial==user.item
              user.pokemon.itemInitial=user.item
              target.pokemon.itemInitial=0
            end
          end
          @battle.pbDisplay(_INTL("{1}'s {2} was transferred to {3}!",
             target.pbThis,PBItems.getName(user.item),user.pbThis(true)))
          PBDebug.log("[Item triggered] #{target.pbThis}'s Sticky Barb moved to #{user.pbThis(true)}")
        end
        if target.hasWorkingItem(:ROCKYHELMET,true) && !user.fainted?
          if !user.hasWorkingAbility(:MAGICGUARD)
            PBDebug.log("[Item triggered] #{target.pbThis}'s Rocky Helmet")
            @battle.scene.pbDamageAnimation(user,0)
            user.pbReduceHP((user.totalhp/6).floor)
            @battle.pbDisplay(_INTL("{1} was hurt by the {2}!",user.pbThis,
               PBItems.getName(target.item)))
          end
        end
        if target.hasWorkingAbility(:AFTERMATH,true) && target.fainted? &&
           !user.fainted?
          if !@battle.pbCheckGlobalAbility(:DAMP) &&
             !user.hasMoldBreaker && !user.hasWorkingAbility(:MAGICGUARD)
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Aftermath")
            @battle.scene.pbDamageAnimation(user,0)
            user.pbReduceHP((user.totalhp/4).floor)
            @battle.pbDisplay(_INTL("{1} was caught in the aftermath!",user.pbThis))
          end
        end
        if target.hasWorkingAbility(:CUTECHARM) && @battle.pbRandom(10)<3
          if !user.fainted? && user.pbCanAttract?(target,false)
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Cute Charm")
            user.pbAttract(target,_INTL("{1}'s {2} made {3} fall in love!",target.pbThis,
               PBAbilities.getName(target.ability),user.pbThis(true)))
          end
        end
        if target.hasWorkingAbility(:EFFECTSPORE,true) && @battle.pbRandom(10)<3
          if USENEWBATTLEMECHANICS &&
             (user.pbHasType?(:GRASS) ||
             user.hasWorkingAbility(:OVERCOAT) ||
             user.hasWorkingItem(:SAFETYGOGGLES))
          else
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Effect Spore")
            case @battle.pbRandom(3)
            when 0
              if user.pbCanPoison?(nil,false)
                user.pbPoison(target,_INTL("{1}'s {2} poisoned {3}!",target.pbThis,
                   PBAbilities.getName(target.ability),user.pbThis(true)))
              end
            when 1
              if user.pbCanSleep?(nil,false)
                user.pbSleep(_INTL("{1}'s {2} made {3} fall asleep!",target.pbThis,
                   PBAbilities.getName(target.ability),user.pbThis(true)))
              end
            when 2
              if user.pbCanParalyze?(nil,false)
                user.pbParalyze(target,_INTL("{1}'s {2} paralyzed {3}! It may be unable to move!",
                   target.pbThis,PBAbilities.getName(target.ability),user.pbThis(true)))
              end
            end
          end
        end
        if target.hasWorkingAbility(:FLAMEBODY,true) && @battle.pbRandom(10)<3 &&
           user.pbCanBurn?(nil,false)
          PBDebug.log("[Ability triggered] #{target.pbThis}'s Flame Body")
          user.pbBurn(target,_INTL("{1}'s {2} burned {3}!",target.pbThis,
             PBAbilities.getName(target.ability),user.pbThis(true)))
        end
        if target.hasWorkingAbility(:MUMMY,true) && !user.fainted?
          if !isConst?(user.ability,PBAbilities,:MULTITYPE) &&
             !isConst?(user.ability,PBAbilities,:STANCECHANGE) &&
             !isConst?(user.ability,PBAbilities,:MUMMY)
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Mummy copied onto #{user.pbThis(true)}")
            user.ability=getConst(PBAbilities,:MUMMY) || 0
            @battle.pbDisplay(_INTL("{1} was mummified by {2}!",
               user.pbThis,target.pbThis(true)))
          end
        end
        if target.hasWorkingAbility(:POISONPOINT,true) && @battle.pbRandom(10)<3 &&
           user.pbCanPoison?(nil,false)
          PBDebug.log("[Ability triggered] #{target.pbThis}'s #{PBAbilities.getName(target.ability)}")
          user.pbPoison(target,_INTL("{1}'s {2} poisoned {3}!",target.pbThis,
             PBAbilities.getName(target.ability),user.pbThis(true)))
        end
        if (target.hasWorkingAbility(:ROUGHSKIN,true) ||
           target.hasWorkingAbility(:IRONBARBS,true)) && !user.fainted?
          if !user.hasWorkingAbility(:MAGICGUARD)
            PBDebug.log("[Ability triggered] #{target.pbThis}'s #{PBAbilities.getName(target.ability)}")
            @battle.scene.pbDamageAnimation(user,0)
            user.pbReduceHP((user.totalhp/8).floor)
            @battle.pbDisplay(_INTL("{1}'s {2} hurt {3}!",target.pbThis,
               PBAbilities.getName(target.ability),user.pbThis(true)))
          end
        end
        if target.hasWorkingAbility(:STATIC,true) && @battle.pbRandom(10)<3 &&
           user.pbCanParalyze?(nil,false)
          PBDebug.log("[Ability triggered] #{target.pbThis}'s Static")
          user.pbParalyze(target,_INTL("{1}'s {2} paralyzed {3}! It may be unable to move!",
             target.pbThis,PBAbilities.getName(target.ability),user.pbThis(true)))
        end
        if target.hasWorkingAbility(:GOOEY,true)
          if user.pbReduceStatWithCause(PBStats::SPEED,1,target,PBAbilities.getName(target.ability))
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Gooey")
          end
        end
        if user.hasWorkingAbility(:POISONTOUCH,true) &&
           target.pbCanPoison?(nil,false) && @battle.pbRandom(10)<3
          PBDebug.log("[Ability triggered] #{user.pbThis}'s Poison Touch")
          target.pbPoison(user,_INTL("{1}'s {2} poisoned {3}!",user.pbThis,
             PBAbilities.getName(user.ability),target.pbThis(true)))
        end
      end
    end
    if damage>0
      if !target.damagestate.substitute
        if target.hasWorkingAbility(:CURSEDBODY,true) && @battle.pbRandom(10)<3
          if user.effects[PBEffects::Disable]<=0 && move.pp>0 && !user.fainted?
            user.effects[PBEffects::Disable]=3
            user.effects[PBEffects::DisableMove]=move.id
            @battle.pbDisplay(_INTL("{1}'s {2} disabled {3}!",target.pbThis,
               PBAbilities.getName(target.ability),user.pbThis(true)))
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Cursed Body disabled #{user.pbThis(true)}")
          end
        end
        if target.hasWorkingAbility(:JUSTIFIED) && isConst?(movetype,PBTypes,:DARK)
          if target.pbIncreaseStatWithCause(PBStats::ATTACK,1,target,PBAbilities.getName(target.ability))
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Justified")
          end
        end
        if target.hasWorkingAbility(:RATTLED) &&
           (isConst?(movetype,PBTypes,:BUG) ||
            isConst?(movetype,PBTypes,:DARK) ||
            isConst?(movetype,PBTypes,:GHOST))
          if target.pbIncreaseStatWithCause(PBStats::SPEED,1,target,PBAbilities.getName(target.ability))
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Rattled")
          end
        end
        if target.hasWorkingAbility(:WEAKARMOR) && move.pbIsPhysical?(movetype)
          if target.pbReduceStatWithCause(PBStats::DEFENSE,1,target,PBAbilities.getName(target.ability))
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Weak Armor (lower Defense)")
          end
          if target.pbIncreaseStatWithCause(PBStats::SPEED,1,target,PBAbilities.getName(target.ability))
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Weak Armor (raise Speed)")
          end
        end
        if target.hasWorkingItem(:AIRBALLOON,true)
          PBDebug.log("[Item triggered] #{target.pbThis}'s Air Balloon popped")
          @battle.pbDisplay(_INTL("{1}'s Air Balloon popped!",target.pbThis))
          target.pbConsumeItem(true,false)
        elsif target.hasWorkingItem(:ABSORBBULB) && isConst?(movetype,PBTypes,:WATER)
          if target.pbIncreaseStatWithCause(PBStats::SPATK,1,target,PBItems.getName(target.item))
            PBDebug.log("[Item triggered] #{target.pbThis}'s #{PBItems.getName(target.item)}")
            target.pbConsumeItem
          end
        elsif target.hasWorkingItem(:LUMINOUSMOSS) && isConst?(movetype,PBTypes,:WATER)
          if target.pbIncreaseStatWithCause(PBStats::SPDEF,1,target,PBItems.getName(target.item))
            PBDebug.log("[Item triggered] #{target.pbThis}'s #{PBItems.getName(target.item)}")
            target.pbConsumeItem
          end
        elsif target.hasWorkingItem(:CELLBATTERY) && isConst?(movetype,PBTypes,:ELECTRIC)
          if target.pbIncreaseStatWithCause(PBStats::ATTACK,1,target,PBItems.getName(target.item))
            PBDebug.log("[Item triggered] #{target.pbThis}'s #{PBItems.getName(target.item)}")
            target.pbConsumeItem
          end
        elsif target.hasWorkingItem(:SNOWBALL) && isConst?(movetype,PBTypes,:ICE)
          if target.pbIncreaseStatWithCause(PBStats::ATTACK,1,target,PBItems.getName(target.item))
            PBDebug.log("[Item triggered] #{target.pbThis}'s #{PBItems.getName(target.item)}")
            target.pbConsumeItem
          end
        elsif target.hasWorkingItem(:WEAKNESSPOLICY) && target.damagestate.typemod>8
          showanim=true
          if target.pbIncreaseStatWithCause(PBStats::ATTACK,2,target,PBItems.getName(target.item),showanim)
            PBDebug.log("[Item triggered] #{target.pbThis}'s Weakness Policy (Attack)")
            showanim=false
          end
          if target.pbIncreaseStatWithCause(PBStats::SPATK,2,target,PBItems.getName(target.item),showanim)
            PBDebug.log("[Item triggered] #{target.pbThis}'s Weakness Policy (Special Attack)")
            showanim=false
          end
          target.pbConsumeItem if !showanim
        elsif target.hasWorkingItem(:ENIGMABERRY) && target.damagestate.typemod>8
          target.pbActivateBerryEffect
        elsif (target.hasWorkingItem(:JABOCABERRY) && move.pbIsPhysical?(movetype)) ||
              (target.hasWorkingItem(:ROWAPBERRY) && move.pbIsSpecial?(movetype))
          if !user.hasWorkingAbility(:MAGICGUARD) && !user.fainted?
            PBDebug.log("[Item triggered] #{target.pbThis}'s #{PBItems.getName(target.item)}")
            @battle.scene.pbDamageAnimation(user,0)
            user.pbReduceHP((user.totalhp/8).floor)
            @battle.pbDisplay(_INTL("{1} consumed its {2} and hurt {3}!",target.pbThis,
               PBItems.getName(target.item),user.pbThis(true)))
            target.pbConsumeItem
          end
        elsif target.hasWorkingItem(:KEEBERRY) && move.pbIsPhysical?(movetype)
          target.pbActivateBerryEffect
        elsif target.hasWorkingItem(:MARANGABERRY) && move.pbIsSpecial?(movetype)
          target.pbActivateBerryEffect
        end
      end
      if target.hasWorkingAbility(:ANGERPOINT)
        if target.damagestate.critical && !target.damagestate.substitute &&
           target.pbCanIncreaseStatStage?(PBStats::ATTACK,target)
          PBDebug.log("[Ability triggered] #{target.pbThis}'s Anger Point")
          target.stages[PBStats::ATTACK]=6
          @battle.pbCommonAnimation("StatUp",target,nil)
          @battle.pbDisplay(_INTL("{1}'s {2} maxed its {3}!",
             target.pbThis,PBAbilities.getName(target.ability),PBStats.getName(PBStats::ATTACK)))
        end
      end
    end
    user.pbAbilityCureCheck
    target.pbAbilityCureCheck
  end

  def pbEffectsAfterHit(user,target,thismove,turneffects)
    return if turneffects[PBEffects::TotalDamage]==0
    if !(user.hasWorkingAbility(:SHEERFORCE) && thismove.addlEffect>0)
      # Target's held items:
      # Red Card
      if target.hasWorkingItem(:REDCARD) && @battle.pbCanSwitch?(user.index,-1,false)
        user.effects[PBEffects::Roar]=true
        @battle.pbDisplay(_INTL("{1} held up its {2} against the {3}!",
           target.pbThis,PBItems.getName(target.item),user.pbThis(true)))
        target.pbConsumeItem
      # Eject Button
      elsif target.hasWorkingItem(:EJECTBUTTON) && @battle.pbCanChooseNonActive?(target.index)
        target.effects[PBEffects::Uturn]=true
        @battle.pbDisplay(_INTL("{1} is switched out with the {2}!",
           target.pbThis,PBItems.getName(target.item)))
        target.pbConsumeItem
      end
      # User's held items:
      # Shell Bell
      if user.hasWorkingItem(:SHELLBELL) && user.effects[PBEffects::HealBlock]==0
        PBDebug.log("[Item triggered] #{user.pbThis}'s Shell Bell (total damage=#{turneffects[PBEffects::TotalDamage]})")
        hpgain=user.pbRecoverHP((turneffects[PBEffects::TotalDamage]/8).floor,true)
        if hpgain>0
          @battle.pbDisplay(_INTL("{1} restored a little HP using its {2}!",
             user.pbThis,PBItems.getName(user.item)))
        end
      end
      # Life Orb
      if user.effects[PBEffects::LifeOrb] && !user.hasWorkingAbility(:MAGICGUARD)
        PBDebug.log("[Item triggered] #{user.pbThis}'s Life Orb (recoil)")
        hploss=user.pbReduceHP((user.totalhp/10).floor,true)
        if hploss>0
          @battle.pbDisplay(_INTL("{1} lost some of its HP!",user.pbThis))
        end
      end
      user.pbFaint if user.fainted? # no return
      # Color Change
      movetype=thismove.pbType(thismove.type,user,target)
      if target.hasWorkingAbility(:COLORCHANGE) &&
         !PBTypes.isPseudoType?(movetype) && !target.pbHasType?(movetype)
        PBDebug.log("[Ability triggered] #{target.pbThis}'s Color Change made it #{PBTypes.getName(movetype)}-type")
        target.type1=movetype
        target.type2=movetype
        target.effects[PBEffects::Type3]=-1
        @battle.pbDisplay(_INTL("{1}'s {2} made it the {3} type!",target.pbThis,
           PBAbilities.getName(target.ability),PBTypes.getName(movetype)))
      end
    end
    # Moxie
    if user.hasWorkingAbility(:MOXIE) && target.fainted?
      if user.pbIncreaseStatWithCause(PBStats::ATTACK,1,user,PBAbilities.getName(user.ability))
        PBDebug.log("[Ability triggered] #{user.pbThis}'s Moxie")
      end
    end
    # Magician
    if user.hasWorkingAbility(:MAGICIAN)
      if target.item>0 && user.item==0 &&
         user.effects[PBEffects::Substitute]==0 &&
         target.effects[PBEffects::Substitute]==0 &&
         !target.hasWorkingAbility(:STICKYHOLD) &&
         !@battle.pbIsUnlosableItem(target,target.item) &&
         !@battle.pbIsUnlosableItem(user,target.item) &&
         (@battle.opponent || !@battle.pbIsOpposing?(user.index))
        user.item=target.item
        target.item=0
        target.effects[PBEffects::Unburden]=true
        if !@battle.opponent &&   # In a wild battle
           user.pokemon.itemInitial==0 &&
           target.pokemon.itemInitial==user.item
          user.pokemon.itemInitial=user.item
          target.pokemon.itemInitial=0
        end
        @battle.pbDisplay(_INTL("{1} stole {2}'s {3} with {4}!",user.pbThis,
           target.pbThis(true),PBItems.getName(user.item),PBAbilities.getName(user.ability)))
        PBDebug.log("[Ability triggered] #{user.pbThis}'s Magician stole #{target.pbThis(true)}'s #{PBItems.getName(user.item)}")
      end
    end
    # Pickpocket
    if target.hasWorkingAbility(:PICKPOCKET)
      if target.item==0 && user.item>0 &&
         user.effects[PBEffects::Substitute]==0 &&
         target.effects[PBEffects::Substitute]==0 &&
         !user.hasWorkingAbility(:STICKYHOLD) &&
         !@battle.pbIsUnlosableItem(user,user.item) &&
         !@battle.pbIsUnlosableItem(target,user.item) &&
         (@battle.opponent || !@battle.pbIsOpposing?(target.index))
        target.item=user.item
        user.item=0
        user.effects[PBEffects::Unburden]=true
        if !@battle.opponent &&   # In a wild battle
           target.pokemon.itemInitial==0 &&
           user.pokemon.itemInitial==target.item
          target.pokemon.itemInitial=target.item
          user.pokemon.itemInitial=0
        end
        @battle.pbDisplay(_INTL("{1} pickpocketed {2}'s {3}!",target.pbThis,
           user.pbThis(true),PBItems.getName(target.item)))
        PBDebug.log("[Ability triggered] #{target.pbThis}'s Pickpocket stole #{user.pbThis(true)}'s #{PBItems.getName(target.item)}")
      end
    end
  end

  def pbAbilityCureCheck
    return if fainted?
    case self.status
    when PBStatuses::SLEEP
      if self.hasWorkingAbility(:VITALSPIRIT) || self.hasWorkingAbility(:INSOMNIA)
        PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)}")
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} woke it up!",pbThis,PBAbilities.getName(@ability)))
      end
    when PBStatuses::POISON
      if self.hasWorkingAbility(:IMMUNITY)
        PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)}")
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} cured its poisoning!",pbThis,PBAbilities.getName(@ability)))
      end
    when PBStatuses::BURN
      if self.hasWorkingAbility(:WATERVEIL)
        PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)}")
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} healed its burn!",pbThis,PBAbilities.getName(@ability)))
      end
    when PBStatuses::PARALYSIS
      if self.hasWorkingAbility(:LIMBER)
        PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)}")
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} cured its paralysis!",pbThis,PBAbilities.getName(@ability)))
      end
    when PBStatuses::FROZEN
      if self.hasWorkingAbility(:MAGMAARMOR)
        PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)}")
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} defrosted it!",pbThis,PBAbilities.getName(@ability)))
      end
    end
    if @effects[PBEffects::Confusion]>0 && self.hasWorkingAbility(:OWNTEMPO)
      PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)} (attract)")
      pbCureConfusion(false)
      @battle.pbDisplay(_INTL("{1}'s {2} snapped it out of its confusion!",pbThis,PBAbilities.getName(@ability)))
    end
    if @effects[PBEffects::Attract]>=0 && self.hasWorkingAbility(:OBLIVIOUS)
      PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)}")
      pbCureAttract
      @battle.pbDisplay(_INTL("{1}'s {2} cured its infatuation status!",pbThis,PBAbilities.getName(@ability)))
    end
    if USENEWBATTLEMECHANICS && @effects[PBEffects::Taunt]>0 && self.hasWorkingAbility(:OBLIVIOUS)
      PBDebug.log("[Ability triggered] #{pbThis}'s #{PBAbilities.getName(@ability)} (taunt)")
      @effects[PBEffects::Taunt]=0
      @battle.pbDisplay(_INTL("{1}'s {2} made its taunt wear off!",pbThis,PBAbilities.getName(@ability)))
    end
  end

################################################################################
# Held item effects
################################################################################
  def pbConsumeItem(recycle=true,pickup=true)
    itemname=PBItems.getName(self.item)
    @pokemon.itemRecycle=self.item if recycle
    @pokemon.itemInitial=0 if @pokemon.itemInitial==self.item
    if pickup
      @effects[PBEffects::PickupItem]=self.item
      @effects[PBEffects::PickupUse]=@battle.nextPickupUse
    end
    self.item=0
    self.effects[PBEffects::Unburden]=true
    # Symbiosis
    if pbPartner && pbPartner.hasWorkingAbility(:SYMBIOSIS) && recycle
      if pbPartner.item>0 &&
         !@battle.pbIsUnlosableItem(pbPartner,pbPartner.item) &&
         !@battle.pbIsUnlosableItem(self,pbPartner.item)
        @battle.pbDisplay(_INTL("{1}'s {2} let it share its {3} with {4}!",
           pbPartner.pbThis,PBAbilities.getName(pbPartner.ability),
           PBItems.getName(pbPartner.item),pbThis(true)))
        self.item=pbPartner.item
        pbPartner.item=0
        pbPartner.effects[PBEffects::Unburden]=true
        pbBerryCureCheck
      end
    end
  end

  def pbConfusionBerry(flavor,message1,message2)
    return false if @effects[PBEffects::HealBlock]>0
    amt=self.pbRecoverHP((self.totalhp/8).floor,true)
    if amt>0
      @battle.pbDisplay(message1)
      if (self.nature%5)==flavor && (self.nature/5).floor!=(self.nature%5)
        @battle.pbDisplay(message2)
        pbConfuseSelf
      end
      return true
    end
    return false
  end

  def pbStatIncreasingBerry(stat,berryname)
    return pbIncreaseStatWithCause(stat,1,self,berryname)
  end

  def pbActivateBerryEffect(berry=0,consume=true)
    berry=self.item if berry==0
    berryname=(berry==0) ? "" : PBItems.getName(berry)
    PBDebug.log("[Item triggered] #{pbThis}'s #{berryname}")
    consumed=false
    if isConst?(berry,PBItems,:ORANBERRY)
      if @effects[PBEffects::HealBlock]==0
        amt=self.pbRecoverHP(10,true)
        if amt>0
          @battle.pbDisplay(_INTL("{1} restored its health using its {2}!",pbThis,berryname))
          consumed=true
        end
      end
    elsif isConst?(berry,PBItems,:SITRUSBERRY) ||
          isConst?(berry,PBItems,:ENIGMABERRY)
      if @effects[PBEffects::HealBlock]==0
        amt=self.pbRecoverHP((self.totalhp/4).floor,true)
        if amt>0
          @battle.pbDisplay(_INTL("{1} restored its health using its {2}!",pbThis,berryname))
          consumed=true
        end
      end
    elsif isConst?(berry,PBItems,:CHESTOBERRY)
      if self.status==PBStatuses::SLEEP
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} cured its sleep problem.",pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:PECHABERRY)
      if self.status==PBStatuses::POISON
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} cured its poisoning.",pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:RAWSTBERRY)
      if self.status==PBStatuses::BURN
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} healed its burn.",pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:CHERIBERRY)
      if self.status==PBStatuses::PARALYSIS
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} cured its paralysis.",pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:ASPEARBERRY)
      if self.status==PBStatuses::FROZEN
        pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1}'s {2} thawed it out.",pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:LEPPABERRY)
      found=[]
      for i in 0...@pokemon.moves.length
        if @pokemon.moves[i].id!=0
          if (consume && @pokemon.moves[i].pp==0) ||
             (!consume && @pokemon.moves[i].pp<@pokemon.moves[i].totalpp)
            found.push(i)
          end
        end
      end
      if found.length>0
        choice=(consume) ? found[0] : found[@battle.pbRandom(found.length)]
        pokemove=@pokemon.moves[choice]
        pokemove.pp+=10
        pokemove.pp=pokemove.totalpp if pokemove.pp>pokemove.totalpp 
        self.moves[choice].pp=pokemove.pp
        movename=PBMoves.getName(pokemove.id)
        @battle.pbDisplay(_INTL("{1}'s {2} restored {3}'s PP!",pbThis,berryname,movename)) 
        consumed=true
      end
    elsif isConst?(berry,PBItems,:PERSIMBERRY)
      if @effects[PBEffects::Confusion]>0
        pbCureConfusion(false)
        @battle.pbDisplay(_INTL("{1}'s {2} snapped it out of its confusion!",pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:LUMBERRY)
      if self.status>0 || @effects[PBEffects::Confusion]>0
        st=self.status; conf=(@effects[PBEffects::Confusion]>0)
        pbCureStatus(false)
        pbCureConfusion(false)
        case st
        when PBStatuses::SLEEP
          @battle.pbDisplay(_INTL("{1}'s {2} woke it up!",pbThis,berryname))
        when PBStatuses::POISON
          @battle.pbDisplay(_INTL("{1}'s {2} cured its poisoning!",pbThis,berryname))
        when PBStatuses::BURN
          @battle.pbDisplay(_INTL("{1}'s {2} healed its burn!",pbThis,berryname))
        when PBStatuses::PARALYSIS
          @battle.pbDisplay(_INTL("{1}'s {2} cured its paralysis!",pbThis,berryname))
        when PBStatuses::FROZEN
          @battle.pbDisplay(_INTL("{1}'s {2} defrosted it!",pbThis,berryname))
        end
        if conf
          @battle.pbDisplay(_INTL("{1}'s {2} snapped it out of its confusion!",pbThis,berryname))
        end
        consumed=true
      end
    elsif isConst?(berry,PBItems,:FIGYBERRY)
      consumed=pbConfusionBerry(0,
         _INTL("{1}'s {2} restored health!",pbThis,berryname),
         _INTL("For {1}, the {2} was too spicy!",pbThis(true),berryname))
    elsif isConst?(berry,PBItems,:WIKIBERRY)
      consumed=pbConfusionBerry(3,
         _INTL("{1}'s {2} restored health!",pbThis,berryname),
         _INTL("For {1}, the {2} was too dry!",pbThis(true),berryname))
    elsif isConst?(berry,PBItems,:MAGOBERRY)
      consumed=pbConfusionBerry(2,
         _INTL("{1}'s {2} restored health!",pbThis,berryname),
         _INTL("For {1}, the {2} was too sweet!",pbThis(true),berryname))
    elsif isConst?(berry,PBItems,:AGUAVBERRY)
      consumed=pbConfusionBerry(4,
         _INTL("{1}'s {2} restored health!",pbThis,berryname),
         _INTL("For {1}, the {2} was too bitter!",pbThis(true),berryname))
    elsif isConst?(berry,PBItems,:IAPAPABERRY)
      consumed=pbConfusionBerry(1,
         _INTL("{1}'s {2} restored health!",pbThis,berryname),
         _INTL("For {1}, the {2} was too sour!",pbThis(true),berryname))
    elsif isConst?(berry,PBItems,:LIECHIBERRY)
      consumed=pbStatIncreasingBerry(PBStats::ATTACK,berryname)
    elsif isConst?(berry,PBItems,:GANLONBERRY) ||
          isConst?(berry,PBItems,:KEEBERRY)
      consumed=pbStatIncreasingBerry(PBStats::DEFENSE,berryname)
    elsif isConst?(berry,PBItems,:SALACBERRY)
      consumed=pbStatIncreasingBerry(PBStats::SPEED,berryname)
    elsif isConst?(berry,PBItems,:PETAYABERRY)
      consumed=pbStatIncreasingBerry(PBStats::SPATK,berryname)
    elsif isConst?(berry,PBItems,:APICOTBERRY) ||
          isConst?(berry,PBItems,:MARANGABERRY)
      consumed=pbStatIncreasingBerry(PBStats::SPDEF,berryname)
    elsif isConst?(berry,PBItems,:LANSATBERRY)
      if @effects[PBEffects::FocusEnergy]<2
        @effects[PBEffects::FocusEnergy]=2
        @battle.pbDisplay(_INTL("{1} used its {2} to get pumped!",pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:MICLEBERRY)
      if !@effects[PBEffects::MicleBerry]
        @effects[PBEffects::MicleBerry]=true
        @battle.pbDisplay(_INTL("{1} boosted the accuracy of its next move using its {2}!",
           pbThis,berryname))
        consumed=true
      end
    elsif isConst?(berry,PBItems,:STARFBERRY)
      stats=[]
      for i in [PBStats::ATTACK,PBStats::DEFENSE,PBStats::SPATK,PBStats::SPDEF,PBStats::SPEED]
        stats.push(i) if pbCanIncreaseStatStage?(i,self)
      end
      if stats.length>0
        stat=stats[@battle.pbRandom(stats.length)]
        consumed=pbIncreaseStatWithCause(stat,2,self,berryname)
      end
    end
    if consumed
      # Cheek Pouch
      if hasWorkingAbility(:CHEEKPOUCH) && @effects[PBEffects::HealBlock]==0
        amt=self.pbRecoverHP((@totalhp/3).floor,true)
        if amt>0
          @battle.pbDisplay(_INTL("{1}'s {2} restored its health!",
             pbThis,PBAbilities.getName(ability)))
        end
      end
      pbConsumeItem if consume
      self.pokemon.belch=true if self.pokemon
    end
  end

  def pbBerryCureCheck(hpcure=false)
    return if fainted?
    unnerver=(pbOpposing1.hasWorkingAbility(:UNNERVE) ||
              pbOpposing2.hasWorkingAbility(:UNNERVE))
    itemname=(self.item==0) ? "" : PBItems.getName(self.item)
    if hpcure
      if self.hasWorkingItem(:BERRYJUICE) && self.hp<=(self.totalhp/2).floor
        amt=self.pbRecoverHP(20,true)
        if amt>0
          @battle.pbCommonAnimation("UseItem",self,nil)
          @battle.pbDisplay(_INTL("{1} restored its health using its {2}!",pbThis,itemname))
          pbConsumeItem
          return
        end
      end
    end
    if !unnerver
      if hpcure 
        if self.hp<=(self.totalhp/2).floor
          if self.hasWorkingItem(:ORANBERRY) ||
             self.hasWorkingItem(:SITRUSBERRY)
            pbActivateBerryEffect
            return
          end
          if self.hasWorkingItem(:FIGYBERRY) ||
             self.hasWorkingItem(:WIKIBERRY) ||
             self.hasWorkingItem(:MAGOBERRY) ||
             self.hasWorkingItem(:AGUAVBERRY) ||
             self.hasWorkingItem(:IAPAPABERRY)
            pbActivateBerryEffect
            return
          end
        end
      end
      if (self.hasWorkingAbility(:GLUTTONY) && self.hp<=(self.totalhp/2).floor) ||
         self.hp<=(self.totalhp/4).floor
        if self.hasWorkingItem(:LIECHIBERRY) ||
           self.hasWorkingItem(:GANLONBERRY) ||
           self.hasWorkingItem(:SALACBERRY) ||
           self.hasWorkingItem(:PETAYABERRY) ||
           self.hasWorkingItem(:APICOTBERRY)
          pbActivateBerryEffect
          return
        end
        if self.hasWorkingItem(:LANSATBERRY) ||
           self.hasWorkingItem(:STARFBERRY)
          pbActivateBerryEffect
          return
        end
        if self.hasWorkingItem(:MICLEBERRY)
          pbActivateBerryEffect
          return
        end
      end
      if self.hasWorkingItem(:LEPPABERRY)
        pbActivateBerryEffect
        return
      end
      if self.hasWorkingItem(:CHESTOBERRY) ||
         self.hasWorkingItem(:PECHABERRY) ||
         self.hasWorkingItem(:RAWSTBERRY) ||
         self.hasWorkingItem(:CHERIBERRY) ||
         self.hasWorkingItem(:ASPEARBERRY) ||
         self.hasWorkingItem(:PERSIMBERRY) ||
         self.hasWorkingItem(:LUMBERRY)
        pbActivateBerryEffect
        return
      end
    end
    if self.hasWorkingItem(:WHITEHERB)
      reducedstats=false
      for i in [PBStats::ATTACK,PBStats::DEFENSE,
                PBStats::SPEED,PBStats::SPATK,PBStats::SPDEF,
                PBStats::ACCURACY,PBStats::EVASION]
        if @stages[i]<0
          @stages[i]=0; reducedstats=true
        end
      end
      if reducedstats
        PBDebug.log("[Item triggered] #{pbThis}'s #{itemname}")
        @battle.pbCommonAnimation("UseItem",self,nil)
        @battle.pbDisplay(_INTL("{1} restored its status using its {2}!",pbThis,itemname))
        pbConsumeItem
        return
      end
    end
    if self.hasWorkingItem(:MENTALHERB) &&
       (@effects[PBEffects::Attract]>=0 ||
       @effects[PBEffects::Taunt]>0 ||
       @effects[PBEffects::Encore]>0 ||
       @effects[PBEffects::Torment] ||
       @effects[PBEffects::Disable]>0 ||
       @effects[PBEffects::HealBlock]>0)
      PBDebug.log("[Item triggered] #{pbThis}'s #{itemname}")
      @battle.pbCommonAnimation("UseItem",self,nil)
      @battle.pbDisplay(_INTL("{1} cured its infatuation status using its {2}.",pbThis,itemname)) if @effects[PBEffects::Attract]>=0
      @battle.pbDisplay(_INTL("{1}'s taunt wore off!",pbThis)) if @effects[PBEffects::Taunt]>0
      @battle.pbDisplay(_INTL("{1}'s encore ended!",pbThis)) if @effects[PBEffects::Encore]>0
      @battle.pbDisplay(_INTL("{1}'s torment wore off!",pbThis)) if @effects[PBEffects::Torment]
      @battle.pbDisplay(_INTL("{1} is no longer disabled!",pbThis)) if @effects[PBEffects::Disable]>0
      @battle.pbDisplay(_INTL("{1}'s Heal Block wore off!",pbThis)) if @effects[PBEffects::HealBlock]>0
      self.pbCureAttract
      @effects[PBEffects::Taunt]=0
      @effects[PBEffects::Encore]=0
      @effects[PBEffects::EncoreMove]=0
      @effects[PBEffects::EncoreIndex]=0
      @effects[PBEffects::Torment]=false
      @effects[PBEffects::Disable]=0
      @effects[PBEffects::HealBlock]=0
      pbConsumeItem
      return
    end
    if hpcure && self.hasWorkingItem(:LEFTOVERS) && self.hp!=self.totalhp &&
       @effects[PBEffects::HealBlock]==0
      PBDebug.log("[Item triggered] #{pbThis}'s Leftovers")
      @battle.pbCommonAnimation("UseItem",self,nil)
      pbRecoverHP((self.totalhp/16).floor,true)
      @battle.pbDisplay(_INTL("{1} restored a little HP using its {2}!",pbThis,itemname))
    end
    if hpcure && self.hasWorkingItem(:BLACKSLUDGE)
      if pbHasType?(:POISON)
        if self.hp!=self.totalhp && @effects[PBEffects::HealBlock]==0
          PBDebug.log("[Item triggered] #{pbThis}'s Black Sludge (heal)")
          @battle.pbCommonAnimation("UseItem",self,nil)
          pbRecoverHP((self.totalhp/16).floor,true)
          @battle.pbDisplay(_INTL("{1} restored a little HP using its {2}!",pbThis,itemname))
        end
      elsif !self.hasWorkingAbility(:MAGICGUARD)
        PBDebug.log("[Item triggered] #{pbThis}'s Black Sludge (damage)")
        @battle.pbCommonAnimation("UseItem",self,nil)
        pbReduceHP((self.totalhp/8).floor,true)
        @battle.pbDisplay(_INTL("{1} was hurt by its {2}!",pbThis,itemname))
      end
      pbFaint if fainted?
    end
  end

################################################################################
# Move user and targets
################################################################################
  def pbFindUser(choice,targets)
    move=choice[2]
    target=choice[3]
    user=self   # Normally, the user is self
    # Targets in normal cases
    case pbTarget(move)
    when PBTargets::SingleNonUser
      if target>=0
        targetBattler=@battle.battlers[target]
        if !pbIsOpposing?(targetBattler.index)
          if !pbAddTarget(targets,targetBattler)
            pbAddTarget(targets,pbOpposing2) if !pbAddTarget(targets,pbOpposing1)
          end
        else
          pbAddTarget(targets,targetBattler.pbPartner) if !pbAddTarget(targets,targetBattler)
        end
      else
        pbRandomTarget(targets)
      end
    when PBTargets::SingleOpposing
      if target>=0
        targetBattler=@battle.battlers[target]
        if !pbIsOpposing?(targetBattler.index)
          if !pbAddTarget(targets,targetBattler)
            pbAddTarget(targets,pbOpposing2) if !pbAddTarget(targets,pbOpposing1)
          end
        else
          pbAddTarget(targets,targetBattler.pbPartner) if !pbAddTarget(targets,targetBattler)
        end
      else
        pbRandomTarget(targets)
      end
    when PBTargets::OppositeOpposing
      pbAddTarget(targets,pbOppositeOpposing) if !pbAddTarget(targets,pbOppositeOpposing2)
    when PBTargets::RandomOpposing
      pbRandomTarget(targets)
    when PBTargets::AllOpposing
      # Just pbOpposing1 because partner is determined late
      pbAddTarget(targets,pbOpposing2) if !pbAddTarget(targets,pbOpposing1)
    when PBTargets::AllNonUsers
      for i in 0...4 # not ordered by priority
        pbAddTarget(targets,@battle.battlers[i]) if i!=@index
      end
    when PBTargets::UserOrPartner
      if target>=0 # Pre-chosen target
        targetBattler=@battle.battlers[target]
        pbAddTarget(targets,targetBattler.pbPartner) if !pbAddTarget(targets,targetBattler)
      else
        pbAddTarget(targets,self)
      end
    when PBTargets::Partner
      pbAddTarget(targets,pbPartner)
    else
      move.pbAddTarget(targets,self)
    end
    return user
  end

  def pbChangeUser(thismove,user)
    # Change user to user of Snatch
    if thismove.canSnatch?
      priority=@battle.pbPriority
      for i in priority
        if i.effects[PBEffects::Snatch]
          @battle.pbDisplay(_INTL("{1} snatched {2}'s move!",i.pbThis,user.pbThis(true)))
          PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Snatch made it use #{user.pbThis(true)}'s #{thismove.name}")
          i.effects[PBEffects::Snatch]=false
          target=user
          user=i
          # Snatch's PP is reduced if old user has Pressure
          userchoice=@battle.choices[user.index][1]
          if target.hasWorkingAbility(:PRESSURE) && user.pbIsOpposing?(target.index) && userchoice>=0
            pressuremove=user.moves[userchoice]
            pbSetPP(pressuremove,pressuremove.pp-1) if pressuremove.pp>0
          end
          break if USENEWBATTLEMECHANICS
        end
      end
    end
    return user
  end

  def pbTarget(move)
    target=move.target
    if move.function==0x10D && pbHasType?(:GHOST) # Curse
      target=PBTargets::OppositeOpposing
    end
    return target
  end

  def pbAddTarget(targets,target)
    if !target.fainted?
      targets[targets.length]=target
      return true
    end
    return false
  end

  def pbRandomTarget(targets)
    choices=[]
    pbAddTarget(choices,pbOpposing1)
    pbAddTarget(choices,pbOpposing2)
    if choices.length>0
      pbAddTarget(targets,choices[@battle.pbRandom(choices.length)])
    end
  end

  def pbChangeTarget(thismove,userandtarget,targets)
    priority=@battle.pbPriority
    changeeffect=0
    user=userandtarget[0]
    target=userandtarget[1]
    # Lightningrod
    if targets.length==1 && isConst?(thismove.pbType(thismove.type,user,target),PBTypes,:ELECTRIC) && 
       !target.hasWorkingAbility(:LIGHTNINGROD)
      for i in priority # use Pokémon earliest in priority
        next if user.index==i.index || target.index==i.index
        if i.hasWorkingAbility(:LIGHTNINGROD)
          PBDebug.log("[Ability triggered] #{i.pbThis}'s Lightningrod (change target)")
          target=i # X's Lightningrod took the attack!
          changeeffect=1
          break
        end
      end
    end
    # Storm Drain
    if targets.length==1 && isConst?(thismove.pbType(thismove.type,user,target),PBTypes,:WATER) && 
       !target.hasWorkingAbility(:STORMDRAIN)
      for i in priority # use Pokémon earliest in priority
        next if user.index==i.index || target.index==i.index
        if i.hasWorkingAbility(:STORMDRAIN)
          PBDebug.log("[Ability triggered] #{i.pbThis}'s Storm Drain (change target)")
          target=i # X's Storm Drain took the attack!
          changeeffect=1
          break
        end
      end
    end
    # Change target to user of Follow Me (overrides Magic Coat
    # because check for Magic Coat below uses this target)
    if PBTargets.targetsOneOpponent?(thismove)
      newtarget=nil; strength=100
      for i in priority # use Pokémon latest in priority
        next if !user.pbIsOpposing?(i.index)
        if !i.fainted? && !@battle.switching && !i.effects[PBEffects::SkyDrop] &&
           i.effects[PBEffects::FollowMe]>0 && i.effects[PBEffects::FollowMe]<strength
          PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Follow Me")
          newtarget=i; strength=i.effects[PBEffects::FollowMe]
          changeeffect=0
        end
      end
      target=newtarget if newtarget
    end
    # TODO: Pressure here is incorrect if Magic Coat redirects target
    if user.pbIsOpposing?(target.index) && target.hasWorkingAbility(:PRESSURE)
      PBDebug.log("[Ability triggered] #{target.pbThis}'s Pressure (in pbChangeTarget)")
      user.pbReducePP(thismove) # Reduce PP
    end  
    # Change user to user of Snatch
    if thismove.canSnatch?
      for i in priority
        if i.effects[PBEffects::Snatch]
          @battle.pbDisplay(_INTL("{1} Snatched {2}'s move!",i.pbThis,user.pbThis(true)))
          PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Snatch made it use #{user.pbThis(true)}'s #{thismove.name}")
          i.effects[PBEffects::Snatch]=false
          target=user
          user=i
          # Snatch's PP is reduced if old user has Pressure
          userchoice=@battle.choices[user.index][1]
          if target.hasWorkingAbility(:PRESSURE) && user.pbIsOpposing?(target.index) && userchoice>=0
            PBDebug.log("[Ability triggered] #{target.pbThis}'s Pressure (part of Snatch)")
            pressuremove=user.moves[userchoice]
            pbSetPP(pressuremove,pressuremove.pp-1) if pressuremove.pp>0
          end
        end
      end
    end
    if thismove.canMagicCoat?
      if target.effects[PBEffects::MagicCoat]
        # switch user and target
        PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Magic Coat made it use #{user.pbThis(true)}'s #{thismove.name}")
        changeeffect=3
        tmp=user
        user=target
        target=tmp
        # Magic Coat's PP is reduced if old user has Pressure
        userchoice=@battle.choices[user.index][1]
        if target.hasWorkingAbility(:PRESSURE) && user.pbIsOpposing?(target.index) && userchoice>=0
          PBDebug.log("[Ability triggered] #{target.pbThis}'s Pressure (part of Magic Coat)")
          pressuremove=user.moves[userchoice]
          pbSetPP(pressuremove,pressuremove.pp-1) if pressuremove.pp>0
        end
      elsif !user.hasMoldBreaker && target.hasWorkingAbility(:MAGICBOUNCE)
        # switch user and target
        PBDebug.log("[Ability triggered] #{target.pbThis}'s Magic Bounce made it use #{user.pbThis(true)}'s #{thismove.name}")
        changeeffect=3
        tmp=user
        user=target
        target=tmp
      end
    end
    if changeeffect==1
      @battle.pbDisplay(_INTL("{1}'s {2} took the move!",target.pbThis,PBAbilities.getName(target.ability)))
    elsif changeeffect==3
      @battle.pbDisplay(_INTL("{1} bounced the {2} back!",user.pbThis,thismove.name))
    end
    userandtarget[0]=user
    userandtarget[1]=target
    if !user.hasMoldBreaker && target.hasWorkingAbility(:SOUNDPROOF) &&
       thismove.isSoundBased? &&
       thismove.function!=0xE5 &&   # Perish Song handled elsewhere
       thismove.function!=0x151     # Parting Shot handled elsewhere
      PBDebug.log("[Ability triggered] #{target.pbThis}'s Soundproof blocked #{user.pbThis(true)}'s #{thismove.name}")
      @battle.pbDisplay(_INTL("{1}'s {2} blocks {3}!",target.pbThis,
         PBAbilities.getName(target.ability),thismove.name))
      return false
    end
    return true
  end

################################################################################
# Move PP
################################################################################
  def pbSetPP(move,pp)
    move.pp=pp
    # Not effects[PBEffects::Mimic], since Mimic can't copy Mimic
    if move.thismove && move.id==move.thismove.id && !@effects[PBEffects::Transform]
      move.thismove.pp=pp
    end
  end

  def pbReducePP(move)
    if @effects[PBEffects::TwoTurnAttack]>0 ||
       @effects[PBEffects::Bide]>0 || 
       @effects[PBEffects::Outrage]>0 ||
       @effects[PBEffects::Rollout]>0 ||
       @effects[PBEffects::HyperBeam]>0 ||
       @effects[PBEffects::Uproar]>0
      # No need to reduce PP if two-turn attack
      return true
    end
    return true if move.pp<0   # No need to reduce PP for special calls of moves
    return true if move.totalpp==0   # Infinite PP, can always be used
    return false if move.pp==0
    if move.pp>0
      pbSetPP(move,move.pp-1)
    end
    return true
  end

  def pbReducePPOther(move)
    pbSetPP(move,move.pp-1) if move.pp>0
  end

################################################################################
# Using a move
################################################################################
  def pbObedienceCheck?(choice)   # Returns true if Pokémon obeys, false if won't
    return true if choice[0]!=1
    return true if !@battle.internalbattle
    return true if !@battle.pbOwnedByPlayer?(@index)
    disobedient = false
    # Pokémon may be disobedient; calculate if it is
    badgelevel = 10*(@battle.pbPlayer.numbadges+1)
    badgelevel = PBExperience::MAXLEVEL if @battle.pbPlayer.numbadges>=8
    move = choice[2]
    if @pokemon.isForeign?(@battle.pbPlayer) && @level>badgelevel
      a = ((@level+badgelevel)*@battle.pbRandom(256)/256).floor
      disobedient |= (a>=badgelevel)
    end
    if self.respond_to?("pbHyperModeObedience")
      disobedient |= !self.pbHyperModeObedience(move)
    end
    return true if !disobedient
    # Pokémon is disobedient; make it do something else
    PBDebug.log("[Disobedience] #{pbThis} disobeyed")
    @effects[PBEffects::Rage] = false
    # Do nothing if using Snore/Sleep Talk
    if self.status==PBStatuses::SLEEP && move.pbCanUseWhileAsleep?
      @battle.pbDisplay(_INTL("{1} ignored orders and kept sleeping!",pbThis)) 
      return false
    end
    b = ((@level+badgelevel)*@battle.pbRandom(256)/256).floor
    # Use another move
    if b<badgelevel
      @battle.pbDisplay(_INTL("{1} ignored orders!",pbThis)) 
      return false if !@battle.pbCanShowFightMenu?(@index)
      othermoves = []
      for i in 0...4
        next if i==choice[1]
        othermoves[othermoves.length] = i if @battle.pbCanChooseMove?(@index,i,false)
      end
      return false if othermoves.length==0   # No other move to use; do nothing
      newchoice = othermoves[@battle.pbRandom(othermoves.length)]
      choice[1] = newchoice
      choice[2] = @moves[newchoice]
      choice[3] = -1
      return true
    end
    c = @level-badgelevel
    r = @battle.pbRandom(256)
    # Fall asleep
    if r<c && pbCanSleep?(self,false)
      pbSleepSelf
      @battle.pbDisplay(_INTL("{1} began to nap!",pbThis))
      return false
    end
    r -= c
    # Hurt self in confusion
    if r<c && self.status!=PBStatuses::SLEEP
      @battle.pbDisplay(_INTL("{1} won't obey! It hurt itself in its confusion!",pbThis))
      pbConfusionDamage
      return false
    end
    # Show refusal message and do nothing
    case @battle.pbRandom(4)
    when 0; @battle.pbDisplay(_INTL("{1} won't obey!",pbThis))
    when 1; @battle.pbDisplay(_INTL("{1} turned away!",pbThis))
    when 2; @battle.pbDisplay(_INTL("{1} is loafing around!",pbThis))
    when 3; @battle.pbDisplay(_INTL("{1} pretended not to notice!",pbThis))
    end
    return false
  end

  def pbSuccessCheck(thismove,user,target,turneffects,accuracy=true)
    if user.effects[PBEffects::TwoTurnAttack]>0
      return true
    end
    # TODO: "Before Protect" applies to Counter/Mirror Coat
    if thismove.function==0xDE && target.status!=PBStatuses::SLEEP # Dream Eater
      @battle.pbDisplay(_INTL("{1} wasn't affected!",target.pbThis))
      PBDebug.log("[Move failed] #{user.pbThis}'s Dream Eater's target isn't asleep")
      return false
    end
    if thismove.function==0x113 && user.effects[PBEffects::Stockpile]==0 # Spit Up
      @battle.pbDisplay(_INTL("But it failed to spit up a thing!"))
      PBDebug.log("[Move failed] #{user.pbThis}'s Spit Up did nothing as Stockpile's count is 0")
      return false
    end
    if target.effects[PBEffects::Protect] && thismove.canProtectAgainst? &&
       !target.effects[PBEffects::ProtectNegation]
      @battle.pbDisplay(_INTL("{1} protected itself!",target.pbThis))
      @battle.successStates[user.index].protected=true
      PBDebug.log("[Move failed] #{target.pbThis}'s Protect stopped the attack")
      return false
    end
    p=thismove.priority
    if USENEWBATTLEMECHANICS
      p+=1 if user.hasWorkingAbility(:PRANKSTER) && thismove.pbIsStatus?
      p+=1 if user.hasWorkingAbility(:GALEWINGS) && isConst?(thismove.type,PBTypes,:FLYING)
    end
    if target.pbOwnSide.effects[PBEffects::QuickGuard] && thismove.canProtectAgainst? &&
       p>0 && !target.effects[PBEffects::ProtectNegation]
      @battle.pbDisplay(_INTL("{1} was protected by Quick Guard!",target.pbThis))
      PBDebug.log("[Move failed] The opposing side's Quick Guard stopped the attack")
      return false
    end
    if target.pbOwnSide.effects[PBEffects::WideGuard] &&
       PBTargets.hasMultipleTargets?(thismove) && !thismove.pbIsStatus? &&
       !target.effects[PBEffects::ProtectNegation]
      @battle.pbDisplay(_INTL("{1} was protected by Wide Guard!",target.pbThis))
      PBDebug.log("[Move failed] The opposing side's Wide Guard stopped the attack")
      return false
    end
    if target.pbOwnSide.effects[PBEffects::CraftyShield] && thismove.pbIsStatus? &&
       thismove.function!=0xE5 # Perish Song
      @battle.pbDisplay(_INTL("Crafty Shield protected {1}!",target.pbThis(true)))
      PBDebug.log("[Move failed] The opposing side's Crafty Shield stopped the attack")
      return false
    end
    if target.pbOwnSide.effects[PBEffects::MatBlock] && !thismove.pbIsStatus? &&
       thismove.canProtectAgainst? && !target.effects[PBEffects::ProtectNegation]
      @battle.pbDisplay(_INTL("{1} was blocked by the kicked-up mat!",thismove.name))
      PBDebug.log("[Move failed] The opposing side's Mat Block stopped the attack")
      return false
    end
    # TODO: Mind Reader/Lock-On
    # --Sketch/FutureSight/PsychUp work even on Fly/Bounce/Dive/Dig
    if thismove.pbMoveFailed(user,target) # TODO: Applies to Snore/Fake Out
      @battle.pbDisplay(_INTL("But it failed!"))
      PBDebug.log(sprintf("[Move failed] Failed pbMoveFailed (function code %02X)",thismove.function))
      return false
    end
    # King's Shield (purposely after pbMoveFailed)
    if target.effects[PBEffects::KingsShield] && !thismove.pbIsStatus? &&
       thismove.canProtectAgainst? && !target.effects[PBEffects::ProtectNegation]
      @battle.pbDisplay(_INTL("{1} protected itself!",target.pbThis))
      @battle.successStates[user.index].protected=true
      PBDebug.log("[Move failed] #{target.pbThis}'s King's Shield stopped the attack")
      if thismove.isContactMove?
        user.pbReduceStat(PBStats::ATTACK,2,nil,false)
      end
      return false
    end
    # Spiky Shield
    if target.effects[PBEffects::SpikyShield] && thismove.canProtectAgainst? &&
       !target.effects[PBEffects::ProtectNegation]
      @battle.pbDisplay(_INTL("{1} protected itself!",target.pbThis))
      @battle.successStates[user.index].protected=true
      PBDebug.log("[Move failed] #{user.pbThis}'s Spiky Shield stopped the attack")
      if thismove.isContactMove? && !user.fainted?
        @battle.scene.pbDamageAnimation(user,0)
        amt=user.pbReduceHP((user.totalhp/8).floor)
        @battle.pbDisplay(_INTL("{1} was hurt!",user.pbThis)) if amt>0
      end
      return false
    end
    # Immunity to powder-based moves
    if USENEWBATTLEMECHANICS && thismove.isPowderMove? &&
       (target.pbHasType?(:GRASS) ||
       (!user.hasMoldBreaker && target.hasWorkingAbility(:OVERCOAT)) ||
       target.hasWorkingItem(:SAFETYGOGGLES))
      @battle.pbDisplay(_INTL("It doesn't affect\r\n{1}...",target.pbThis(true)))
      PBDebug.log("[Move failed] #{target.pbThis} is immune to powder-based moves somehow")
      return false
    end
    if thismove.basedamage>0 && thismove.function!=0x02 && # Struggle
       thismove.function!=0x111 # Future Sight
      type=thismove.pbType(thismove.type,user,target)
      typemod=thismove.pbTypeModifier(type,user,target)
      # Airborne-based immunity to Ground moves
      if isConst?(type,PBTypes,:GROUND) && target.isAirborne?(user.hasMoldBreaker) &&
         !target.hasWorkingItem(:RINGTARGET) && thismove.function!=0x11C # Smack Down
        if !user.hasMoldBreaker && target.hasWorkingAbility(:LEVITATE)
          @battle.pbDisplay(_INTL("{1} makes Ground moves miss with Levitate!",target.pbThis))
          PBDebug.log("[Ability triggered] #{target.pbThis}'s Levitate made the Ground-type move miss")
          return false
        end
        if target.hasWorkingItem(:AIRBALLOON)
          @battle.pbDisplay(_INTL("{1}'s Air Balloon makes Ground moves miss!",target.pbThis))
          PBDebug.log("[Item triggered] #{target.pbThis}'s Air Balloon made the Ground-type move miss")
          return false
        end
        if target.effects[PBEffects::MagnetRise]>0
          @battle.pbDisplay(_INTL("{1} makes Ground moves miss with Magnet Rise!",target.pbThis))
          PBDebug.log("[Lingering effect triggered] #{target.pbThis}'s Magnet Rise made the Ground-type move miss")
          return false
        end
        if target.effects[PBEffects::Telekinesis]>0
          @battle.pbDisplay(_INTL("{1} makes Ground moves miss with Telekinesis!",target.pbThis))
          PBDebug.log("[Lingering effect triggered] #{target.pbThis}'s Telekinesis made the Ground-type move miss")
          return false
        end
      end
      if !user.hasMoldBreaker && target.hasWorkingAbility(:WONDERGUARD) &&
         type>=0 && typemod<=8
        @battle.pbDisplay(_INTL("{1} avoided damage with Wonder Guard!",target.pbThis))
        PBDebug.log("[Ability triggered] #{target.pbThis}'s Wonder Guard")
        return false 
      end
      if typemod==0
        @battle.pbDisplay(_INTL("It doesn't affect\r\n{1}...",target.pbThis(true)))
        PBDebug.log("[Move failed] Type immunity")
        return false 
      end
    end
    if accuracy
      if target.effects[PBEffects::LockOn]>0 && target.effects[PBEffects::LockOnPos]==user.index
        PBDebug.log("[Lingering effect triggered] #{target.pbThis}'s Lock-On")
        return true
      end
      miss=false; override=false
      invulmove=PBMoveData.new(target.effects[PBEffects::TwoTurnAttack]).function
      case invulmove
      when 0xC9, 0xCC # Fly, Bounce
        miss=true unless thismove.function==0x08 ||  # Thunder
                         thismove.function==0x15 ||  # Hurricane
                         thismove.function==0x77 ||  # Gust
                         thismove.function==0x78 ||  # Twister
                         thismove.function==0x11B || # Sky Uppercut
                         thismove.function==0x11C || # Smack Down
                         isConst?(thismove.id,PBMoves,:WHIRLWIND)
      when 0xCA # Dig
        miss=true unless thismove.function==0x76 || # Earthquake
                         thismove.function==0x95    # Magnitude
      when 0xCB # Dive
        miss=true unless thismove.function==0x75 || # Surf
                         thismove.function==0xD0    # Whirlpool
      when 0xCD # Shadow Force
        miss=true
      when 0xCE # Sky Drop
        miss=true unless thismove.function==0x08 ||  # Thunder
                         thismove.function==0x15 ||  # Hurricane
                         thismove.function==0x77 ||  # Gust
                         thismove.function==0x78 ||  # Twister
                         thismove.function==0x11B || # Sky Uppercut
                         thismove.function==0x11C    # Smack Down
      when 0x14D # Phantom Force
        miss=true
      end
      if target.effects[PBEffects::SkyDrop]
        miss=true unless thismove.function==0x08 ||  # Thunder
                         thismove.function==0x15 ||  # Hurricane
                         thismove.function==0x77 ||  # Gust
                         thismove.function==0x78 ||  # Twister
                         thismove.function==0xCE ||  # Sky Drop
                         thismove.function==0x11B || # Sky Uppercut
                         thismove.function==0x11C    # Smack Down
      end
      miss=false if user.hasWorkingAbility(:NOGUARD) ||
                    target.hasWorkingAbility(:NOGUARD) ||
                    @battle.futuresight
      override=true if USENEWBATTLEMECHANICS && thismove.function==0x06 && # Toxic
                    thismove.basedamage==0 && user.pbHasType?(:POISON)
      override=true if !miss && turneffects[PBEffects::SkipAccuracyCheck] # Called by another move
      if !override && (miss || !thismove.pbAccuracyCheck(user,target)) # Includes Counter/Mirror Coat
        PBDebug.log(sprintf("[Move failed] Failed pbAccuracyCheck (function code %02X) or target is semi-invulnerable",thismove.function))
        if thismove.target==PBTargets::AllOpposing && 
           (!user.pbOpposing1.fainted? ? 1 : 0) + (!user.pbOpposing2.fainted? ? 1 : 0) > 1
          @battle.pbDisplay(_INTL("{1} avoided the attack!",target.pbThis))
        elsif thismove.target==PBTargets::AllNonUsers && 
           (!user.pbOpposing1.fainted? ? 1 : 0) + (!user.pbOpposing2.fainted? ? 1 : 0) + (!user.pbPartner.fainted? ? 1 : 0) > 1
          @battle.pbDisplay(_INTL("{1} avoided the attack!",target.pbThis))
        elsif target.effects[PBEffects::TwoTurnAttack]>0
          @battle.pbDisplay(_INTL("{1} avoided the attack!",target.pbThis))
        elsif thismove.function==0xDC # Leech Seed
          @battle.pbDisplay(_INTL("{1} evaded the attack!",target.pbThis))
        else
          @battle.pbDisplay(_INTL("{1}'s attack missed!",user.pbThis))
        end
        return false
      end
    end
    return true
  end

  def pbTryUseMove(choice,thismove,turneffects)
    return true if turneffects[PBEffects::PassedTrying]
    # TODO: Return true if attack has been Mirror Coated once already
    if @effects[PBEffects::SkyDrop] # Intentionally no message here
      PBDebug.log("[Move failed] #{pbThis} can't use #{thismove.name} because of being Sky Dropped")
      return false
    end
    if @battle.field.effects[PBEffects::Gravity]>0 && thismove.unusableInGravity?
      @battle.pbDisplay(_INTL("{1} can't use {2} because of gravity!",pbThis,thismove.name))
      PBDebug.log("[Move failed] #{pbThis} can't use #{thismove.name} because of Gravity")
      return false
    end
    if @effects[PBEffects::Taunt]>0 && thismove.basedamage==0
      @battle.pbDisplay(_INTL("{1} can't use {2} after the taunt!",pbThis,thismove.name))
      PBDebug.log("[Move failed] #{pbThis} can't use #{thismove.name} because of Taunt")
      return false
    end
    if @effects[PBEffects::HealBlock]>0 && thismove.isHealingMove?
      @battle.pbDisplay(_INTL("{1} can't use {2} because of Heal Block!",pbThis,thismove.name))
      PBDebug.log("[Move failed] #{pbThis} can't use #{thismove.name} because of Heal Block")
      return false
    end
    if @effects[PBEffects::Torment] && thismove.id==@lastMoveUsed &&
       thismove.id!=@battle.struggle.id && @effects[PBEffects::TwoTurnAttack]==0
      @battle.pbDisplayPaused(_INTL("{1} can't use the same move in a row due to the torment!",pbThis))
      PBDebug.log("[Move failed] #{pbThis} can't use #{thismove.name} because of Torment")
      return false
    end
    if pbOpposing1.effects[PBEffects::Imprison] && !pbOpposing1.fainted?
      if thismove.id==pbOpposing1.moves[0].id ||
         thismove.id==pbOpposing1.moves[1].id ||
         thismove.id==pbOpposing1.moves[2].id ||
         thismove.id==pbOpposing1.moves[3].id
        @battle.pbDisplay(_INTL("{1} can't use the sealed {2}!",pbThis,thismove.name))
        PBDebug.log("[Move failed] #{thismove.name} can't use #{thismove.name} because of #{pbOpposing1.pbThis(true)}'s Imprison")
        return false
      end
    end
    if pbOpposing2.effects[PBEffects::Imprison] && !pbOpposing2.fainted?
      if thismove.id==pbOpposing2.moves[0].id ||
         thismove.id==pbOpposing2.moves[1].id ||
         thismove.id==pbOpposing2.moves[2].id ||
         thismove.id==pbOpposing2.moves[3].id
        @battle.pbDisplay(_INTL("{1} can't use the sealed {2}!",pbThis,thismove.name))
        PBDebug.log("[Move failed] #{thismove.name} can't use #{thismove.name} because of #{pbOpposing2.pbThis(true)}'s Imprison")
        return false
      end
    end
    if @effects[PBEffects::Disable]>0 && thismove.id==@effects[PBEffects::DisableMove] &&
       !@battle.switching # Pursuit ignores if it's disabled
      @battle.pbDisplayPaused(_INTL("{1}'s {2} is disabled!",pbThis,thismove.name))
      PBDebug.log("[Move failed] #{pbThis}'s #{thismove.name} is disabled")
      return false
    end
    if choice[1]==-2 # Battle Palace
      @battle.pbDisplay(_INTL("{1} appears incapable of using its power!",pbThis))
      PBDebug.log("[Move failed] Battle Palace: #{pbThis} is incapable of using its power")
      return false
    end
    if @effects[PBEffects::HyperBeam]>0
      @battle.pbDisplay(_INTL("{1} must recharge!",pbThis))
      PBDebug.log("[Move failed] #{pbThis} must recharge after using #{PokeBattle_Move.pbFromPBMove(@battle,PBMove.new(@currentMove)).name}")
      return false
    end
    if self.hasWorkingAbility(:TRUANT) && @effects[PBEffects::Truant]
      @battle.pbDisplay(_INTL("{1} is loafing around!",pbThis))
      PBDebug.log("[Ability triggered] #{pbThis}'s Truant")
      return false
    end
    if !turneffects[PBEffects::SkipAccuracyCheck]
      if self.status==PBStatuses::SLEEP
        self.statusCount-=1
        if self.statusCount<=0
          self.pbCureStatus
        else
          self.pbContinueStatus
          PBDebug.log("[Status] #{pbThis} remained asleep (count: #{self.statusCount})")
          if !thismove.pbCanUseWhileAsleep? # Snore/Sleep Talk/Outrage
            PBDebug.log("[Move failed] #{pbThis} couldn't use #{thismove.name} while asleep")
            return false
          end
        end
      end
    end
    if self.status==PBStatuses::FROZEN
      if thismove.canThawUser?
        PBDebug.log("[Move effect triggered] #{pbThis} was defrosted by using #{thismove.name}")
        self.pbCureStatus(false)
        @battle.pbDisplay(_INTL("{1} melted the ice!",pbThis))
        pbCheckForm
      elsif @battle.pbRandom(10)<2 && !turneffects[PBEffects::SkipAccuracyCheck]
        self.pbCureStatus
        pbCheckForm
      elsif !thismove.canThawUser?
        self.pbContinueStatus
        PBDebug.log("[Status] #{pbThis} remained frozen and couldn't move")
        return false
      end
    end
    if !turneffects[PBEffects::SkipAccuracyCheck]
      if @effects[PBEffects::Confusion]>0
        @effects[PBEffects::Confusion]-=1
        if @effects[PBEffects::Confusion]<=0
          pbCureConfusion
        else
          pbContinueConfusion
          PBDebug.log("[Status] #{pbThis} remained confused (count: #{@effects[PBEffects::Confusion]})")
          if @battle.pbRandom(2)==0
            pbConfusionDamage
            @battle.pbDisplay(_INTL("It hurt itself in its confusion!")) 
            PBDebug.log("[Status] #{pbThis} hurt itself in its confusion and couldn't move")
            return false
          end
        end
      end
    end
    if @effects[PBEffects::Flinch]
      @effects[PBEffects::Flinch]=false
      @battle.pbDisplay(_INTL("{1} flinched and couldn't move!",self.pbThis))
      PBDebug.log("[Lingering effect triggered] #{pbThis} flinched")
      if self.hasWorkingAbility(:STEADFAST)
        if pbIncreaseStatWithCause(PBStats::SPEED,1,self,PBAbilities.getName(self.ability))
          PBDebug.log("[Ability triggered] #{pbThis}'s Steadfast")
        end
      end
      return false
    end
    if !turneffects[PBEffects::SkipAccuracyCheck]
      if @effects[PBEffects::Attract]>=0
        pbAnnounceAttract(@battle.battlers[@effects[PBEffects::Attract]])
        if @battle.pbRandom(2)==0
          pbContinueAttract
          PBDebug.log("[Lingering effect triggered] #{pbThis} was infatuated and couldn't move")
          return false
        end
      end
      if self.status==PBStatuses::PARALYSIS
        if @battle.pbRandom(4)==0
          pbContinueStatus
          PBDebug.log("[Status] #{pbThis} was fully paralysed and couldn't move")
          return false
        end
      end
    end
    if !turneffects[PBEffects::SkipAccuracyCheck]
      return false if !pbObedienceCheck?(choice)
    end
    turneffects[PBEffects::PassedTrying]=true
    return true
  end

  def pbConfusionDamage
    self.damagestate.reset
    confmove=PokeBattle_Confusion.new(@battle,nil)
    confmove.pbEffect(self,self)
    pbFaint if fainted?
  end

  def pbUpdateTargetedMove(thismove,user)
    # TODO: Snatch, moves that use other moves
    # TODO: All targeting cases
    # Two-turn attacks, Magic Coat, Future Sight, Counter/MirrorCoat/Bide handled
  end

  def pbProcessMoveAgainstTarget(thismove,user,target,numhits,turneffects,nocheck=false,alltargets=nil,showanimation=true)
    realnumhits=0
    totaldamage=0
    destinybond=false
    for i in 0...numhits
      target.damagestate.reset
      # Check success (accuracy/evasion calculation)
      if !nocheck &&
         !pbSuccessCheck(thismove,user,target,turneffects,i==0 || thismove.successCheckPerHit?)
        if thismove.function==0xBF && realnumhits>0   # Triple Kick
          break   # Considered a success if Triple Kick hits at least once
        elsif thismove.function==0x10B   # Hi Jump Kick, Jump Kick
          if !user.hasWorkingAbility(:MAGICGUARD)
            PBDebug.log("[Move effect triggered] #{user.pbThis} took crash damage")
            # TODO: Not shown if message is "It doesn't affect XXX..."
            @battle.pbDisplay(_INTL("{1} kept going and crashed!",user.pbThis))
            damage=(user.totalhp/2).floor
            if damage>0
              @battle.scene.pbDamageAnimation(user,0)
              user.pbReduceHP(damage)
            end
            user.pbFaint if user.fainted?
          end
        end
        user.effects[PBEffects::Outrage]=0 if thismove.function==0xD2 # Outrage
        user.effects[PBEffects::Rollout]=0 if thismove.function==0xD3 # Rollout
        user.effects[PBEffects::FuryCutter]=0 if thismove.function==0x91 # Fury Cutter
        user.effects[PBEffects::Stockpile]=0 if thismove.function==0x113 # Spit Up
        return
      end
      # Add to counters for moves which increase them when used in succession
      if thismove.function==0x91 # Fury Cutter
        user.effects[PBEffects::FuryCutter]+=1 if user.effects[PBEffects::FuryCutter]<4
      else
        user.effects[PBEffects::FuryCutter]=0
      end
      if thismove.function==0x92 # Echoed Voice
        if !user.pbOwnSide.effects[PBEffects::EchoedVoiceUsed] &&
           user.pbOwnSide.effects[PBEffects::EchoedVoiceCounter]<5
          user.pbOwnSide.effects[PBEffects::EchoedVoiceCounter]+=1
        end
        user.pbOwnSide.effects[PBEffects::EchoedVoiceUsed]=true
      end
      # Count a hit for Parental Bond if it applies
      user.effects[PBEffects::ParentalBond]-=1 if user.effects[PBEffects::ParentalBond]>0
      # This hit will happen; count it
      realnumhits+=1
      # Damage calculation and/or main effect
      damage=thismove.pbEffect(user,target,i,alltargets,showanimation) # Recoil/drain, etc. are applied here
      totaldamage+=damage if damage>0
      # Message and consume for type-weakening berries
      if target.damagestate.berryweakened
        @battle.pbDisplay(_INTL("The {1} weakened the damage to {2}!",
           PBItems.getName(target.item),target.pbThis(true)))
        target.pbConsumeItem
      end
      # Illusion
      if target.effects[PBEffects::Illusion] && target.hasWorkingAbility(:ILLUSION) &&
         damage>0 && !target.damagestate.substitute
        PBDebug.log("[Ability triggered] #{target.pbThis}'s Illusion ended")    
        target.effects[PBEffects::Illusion]=nil
        @battle.scene.pbChangePokemon(target,target.pokemon)
        @battle.pbDisplay(_INTL("{1}'s {2} wore off!",target.pbThis,
            PBAbilities.getName(target.ability)))
      end
      user.pbFaint if user.fainted? # no return
      return if numhits>1 && target.damagestate.calcdamage<=0
      @battle.pbJudgeCheckpoint(user,thismove)
      # Additional effect
      if target.damagestate.calcdamage>0 &&
         !user.hasWorkingAbility(:SHEERFORCE) &&
         (user.hasMoldBreaker || !target.hasWorkingAbility(:SHIELDDUST))
        addleffect=thismove.addlEffect
        addleffect*=2 if (user.hasWorkingAbility(:SERENEGRACE) ||
                         user.pbOwnSide.effects[PBEffects::Rainbow]>0) &&
                         thismove.function!=0xA4 # Secret Power
        addleffect=100 if $DEBUG && Input.press?(Input::CTRL)
        if @battle.pbRandom(100)<addleffect
          PBDebug.log("[Move effect triggered] #{thismove.name}'s added effect")
          thismove.pbAdditionalEffect(user,target)
        end
      end
      # Ability effects
      pbEffectsOnDealingDamage(thismove,user,target,damage)
      # Grudge
      if !user.fainted? && target.fainted?
        if target.effects[PBEffects::Grudge] && target.pbIsOpposing?(user.index)
          thismove.pp=0
          @battle.pbDisplay(_INTL("{1}'s {2} lost all its PP due to the grudge!",
             user.pbThis,thismove.name))
          PBDebug.log("[Lingering effect triggered] #{target.pbThis}'s Grudge made #{thismove.name} lose all its PP")
        end
      end
      if target.fainted?
        destinybond=destinybond || target.effects[PBEffects::DestinyBond]
      end
      user.pbFaint if user.fainted? # no return
      break if user.fainted?
      break if target.fainted?
      # Make the target flinch
      if target.damagestate.calcdamage>0 && !target.damagestate.substitute
        if user.hasMoldBreaker || !target.hasWorkingAbility(:SHIELDDUST)
          canflinch=false
          if (user.hasWorkingItem(:KINGSROCK) || user.hasWorkingItem(:RAZORFANG)) &&
             thismove.canKingsRock?
            canflinch=true
          end
          if user.hasWorkingAbility(:STENCH) &&
             thismove.function!=0x09 && # Thunder Fang
             thismove.function!=0x0B && # Fire Fang
             thismove.function!=0x0E && # Ice Fang
             thismove.function!=0x0F && # flinch-inducing moves
             thismove.function!=0x10 && # Stomp
             thismove.function!=0x11 && # Snore
             thismove.function!=0x12 && # Fake Out
             thismove.function!=0x78 && # Twister
             thismove.function!=0xC7    # Sky Attack
            canflinch=true
          end
          if canflinch && @battle.pbRandom(10)==0
            PBDebug.log("[Item/ability triggered] #{user.pbThis}'s King's Rock/Razor Fang or Stench")
            target.pbFlinch(user)
          end
        end
      end
      if target.damagestate.calcdamage>0 && !target.fainted?
        # Defrost
        if target.status==PBStatuses::FROZEN &&
           (isConst?(thismove.pbType(thismove.type,user,target),PBTypes,:FIRE) ||
           (USENEWBATTLEMECHANICS && isConst?(thismove.id,PBMoves,:SCALD)))
          target.pbCureStatus
        end
        # Rage
        if target.effects[PBEffects::Rage] && target.pbIsOpposing?(user.index)
          # TODO: Apparently triggers if opposing Pokémon uses Future Sight after a Future Sight attack
          if target.pbIncreaseStatWithCause(PBStats::ATTACK,1,target,"",true,false)
            PBDebug.log("[Lingering effect triggered] #{target.pbThis}'s Rage")
            @battle.pbDisplay(_INTL("{1}'s rage is building!",target.pbThis))
          end
        end
      end
      target.pbFaint if target.fainted? # no return
      user.pbFaint if user.fainted? # no return
      break if user.fainted? || target.fainted?
      # Berry check (maybe just called by ability effect, since only necessary Berries are checked)
      for j in 0...4
        @battle.battlers[j].pbBerryCureCheck
      end
      break if user.fainted? || target.fainted?
      target.pbUpdateTargetedMove(thismove,user)
      break if target.damagestate.calcdamage<=0
    end
    turneffects[PBEffects::TotalDamage]+=totaldamage if totaldamage>0
    # Battle Arena only - attack is successful
    @battle.successStates[user.index].useState=2
    @battle.successStates[user.index].typemod=target.damagestate.typemod
    # Type effectiveness
    if numhits>1
      if target.damagestate.typemod>8
        if alltargets.length>1
          @battle.pbDisplay(_INTL("It's super effective on {1}!",target.pbThis(true)))
        else
          @battle.pbDisplay(_INTL("It's super effective!"))
        end
      elsif target.damagestate.typemod>=1 && target.damagestate.typemod<8
        if alltargets.length>1
          @battle.pbDisplay(_INTL("It's not very effective on {1}...",target.pbThis(true)))
        else
          @battle.pbDisplay(_INTL("It's not very effective..."))
        end
      end
      if realnumhits==1
        @battle.pbDisplay(_INTL("Hit {1} time!",realnumhits))
      else
        @battle.pbDisplay(_INTL("Hit {1} times!",realnumhits))
      end
    end
    PBDebug.log("Move did #{numhits} hit(s), total damage=#{turneffects[PBEffects::TotalDamage]}")
    # Faint if 0 HP
    target.pbFaint if target.fainted? # no return
    user.pbFaint if user.fainted? # no return
    thismove.pbEffectAfterHit(user,target,turneffects)
    target.pbFaint if target.fainted? # no return
    user.pbFaint if user.fainted? # no return
    # Destiny Bond
    if !user.fainted? && target.fainted?
      if destinybond && target.pbIsOpposing?(user.index)
        PBDebug.log("[Lingering effect triggered] #{target.pbThis}'s Destiny Bond")
        @battle.pbDisplay(_INTL("{1} took its attacker down with it!",target.pbThis))
        user.pbReduceHP(user.hp)
        user.pbFaint # no return
        @battle.pbJudgeCheckpoint(user)
      end
    end
    pbEffectsAfterHit(user,target,thismove,turneffects)
    # Berry check
    for j in 0...4
      @battle.battlers[j].pbBerryCureCheck
    end
    target.pbUpdateTargetedMove(thismove,user)
  end

  def pbUseMoveSimple(moveid,index=-1,target=-1)
    choice=[]
    choice[0]=1       # "Use move"
    choice[1]=index   # Index of move to be used in user's moveset
    choice[2]=PokeBattle_Move.pbFromPBMove(@battle,PBMove.new(moveid)) # PokeBattle_Move object of the move
    choice[2].pp=-1
    choice[3]=target  # Target (-1 means no target yet)
    if index>=0
      @battle.choices[@index][1]=index
    end
    PBDebug.log("#{pbThis} used simple move #{choice[2].name}")
    pbUseMove(choice,true)
    return
  end

  def pbUseMove(choice,specialusage=false)
    # TODO: lastMoveUsed is not to be updated on nested calls
    # Note: user.lastMoveUsedType IS to be updated on nested calls; is used for Conversion 2
    turneffects=[]
    turneffects[PBEffects::SpecialUsage]=specialusage
    turneffects[PBEffects::SkipAccuracyCheck]=(specialusage && choice[2]!=@battle.struggle)
    turneffects[PBEffects::PassedTrying]=false
    turneffects[PBEffects::TotalDamage]=0
    # Start using the move
    pbBeginTurn(choice)
    # Force the use of certain moves if they're already being used
    if @effects[PBEffects::TwoTurnAttack]>0 ||
       @effects[PBEffects::HyperBeam]>0 ||
       @effects[PBEffects::Outrage]>0 ||
       @effects[PBEffects::Rollout]>0 ||
       @effects[PBEffects::Uproar]>0 ||
       @effects[PBEffects::Bide]>0
      choice[2]=PokeBattle_Move.pbFromPBMove(@battle,PBMove.new(@currentMove))
      turneffects[PBEffects::SpecialUsage]=true
      PBDebug.log("Continuing multi-turn move #{choice[2].name}")
    elsif @effects[PBEffects::Encore]>0 && choice[1]>=0
      if @battle.pbCanShowCommands?(@index) &&
         @battle.pbCanChooseMove?(@index,@effects[PBEffects::EncoreIndex],false)
        if choice[1]!=@effects[PBEffects::EncoreIndex] # Was Encored mid-round
          choice[1]=@effects[PBEffects::EncoreIndex]
          choice[2]=@moves[@effects[PBEffects::EncoreIndex]]
          choice[3]=-1 # No target chosen
        end
        PBDebug.log("Using Encored move #{choice[2].name}")
      end
    end
    thismove=choice[2]
    return if !thismove || thismove.id==0   # if move was not chosen
    if !turneffects[PBEffects::SpecialUsage]
      # TODO: Quick Claw message
    end
    # Stance Change
    if hasWorkingAbility(:STANCECHANGE) && isConst?(species,PBSpecies,:AEGISLASH) &&
       !@effects[PBEffects::Transform]
      if thismove.pbIsDamaging? && self.form!=1
        self.form=1
        pbUpdate(true)
        @battle.scene.pbChangePokemon(self,@pokemon)
        @battle.pbDisplay(_INTL("{1} changed to Blade Forme!",pbThis))
        PBDebug.log("[Form changed] #{pbThis} changed to Blade Forme")
      elsif isConst?(thismove.id,PBMoves,:KINGSSHIELD) && self.form!=0
        self.form=0
        pbUpdate(true)
        @battle.scene.pbChangePokemon(self,@pokemon)
        @battle.pbDisplay(_INTL("{1} changed to Shield Forme!",pbThis))
        PBDebug.log("[Form changed] #{pbThis} changed to Shield Forme")
      end      
    end
    # Record that user has used a move this round (ot at least tried to)
    self.lastRoundMoved=@battle.turncount
    # Try to use the move
    if !pbTryUseMove(choice,thismove,turneffects)
      self.lastMoveUsed=-1
      self.lastMoveUsedType=-1
      if !turneffects[PBEffects::SpecialUsage]
        self.lastMoveUsedSketch=-1 if self.effects[PBEffects::TwoTurnAttack]==0
        self.lastRegularMoveUsed=-1
      end
      pbCancelMoves
      @battle.pbGainEXP
      pbEndTurn(choice)
      @battle.pbJudge #      @battle.pbSwitch
      return
    end
    thismove=choice[2]   # Disobedience may have changed the move to be used
    return if !thismove || thismove.id==0   # if move was not chosen
    if !turneffects[PBEffects::SpecialUsage]
      if !pbReducePP(thismove)
        @battle.pbDisplay(_INTL("{1} used\r\n{2}!",pbThis,thismove.name))
        @battle.pbDisplay(_INTL("But there was no PP left for the move!"))
        self.lastMoveUsed=-1
        self.lastMoveUsedType=-1
        self.lastMoveUsedSketch=-1 if self.effects[PBEffects::TwoTurnAttack]==0
        self.lastRegularMoveUsed=-1
        pbEndTurn(choice)
        @battle.pbJudge #        @battle.pbSwitch
        PBDebug.log("[Move failed] #{thismove.name} has no PP left")
        return
      end
    end
    # Remember that user chose a two-turn move
    if thismove.pbTwoTurnAttack(self)
      # Beginning use of two-turn attack
      @effects[PBEffects::TwoTurnAttack]=thismove.id
      @currentMove=thismove.id
    else
      @effects[PBEffects::TwoTurnAttack]=0 # Cancel use of two-turn attack
    end
    # Charge up Metronome item
    if self.lastMoveUsed==thismove.id
      self.effects[PBEffects::Metronome]+=1
    else
      self.effects[PBEffects::Metronome]=0
    end
    # "X used Y!" message
    case thismove.pbDisplayUseMessage(self)
    when 2   # Continuing Bide
      return
    when 1   # Starting Bide
      self.lastMoveUsed=thismove.id
      self.lastMoveUsedType=thismove.pbType(thismove.type,self,nil)
      if !turneffects[PBEffects::SpecialUsage]
        self.lastMoveUsedSketch=thismove.id if self.effects[PBEffects::TwoTurnAttack]==0
        self.lastRegularMoveUsed=thismove.id
      end
      @battle.lastMoveUsed=thismove.id
      @battle.lastMoveUser=self.index
      @battle.successStates[self.index].useState=2
      @battle.successStates[self.index].typemod=8
      return
    when -1   # Was hurt while readying Focus Punch, fails use
      self.lastMoveUsed=thismove.id
      self.lastMoveUsedType=thismove.pbType(thismove.type,self,nil)
      if !turneffects[PBEffects::SpecialUsage]
        self.lastMoveUsedSketch=thismove.id if self.effects[PBEffects::TwoTurnAttack]==0
        self.lastRegularMoveUsed=thismove.id
      end
      @battle.lastMoveUsed=thismove.id
      @battle.lastMoveUser=self.index
      @battle.successStates[self.index].useState=2 # somehow treated as a success
      @battle.successStates[self.index].typemod=8
      PBDebug.log("[Move failed] #{pbThis} was hurt while readying Focus Punch")
      return
    end
    # Find the user and target(s)
    targets=[]
    user=pbFindUser(choice,targets)
    # Battle Arena only - assume failure 
    @battle.successStates[user.index].useState=1
    @battle.successStates[user.index].typemod=8
    # Check whether Selfdestruct works
    if !thismove.pbOnStartUse(user) # Selfdestruct, Natural Gift, Beat Up can return false here
      PBDebug.log(sprintf("[Move failed] Failed pbOnStartUse (function code %02X)",thismove.function))
      user.lastMoveUsed=thismove.id
      user.lastMoveUsedType=thismove.pbType(thismove.type,user,nil)
      if !turneffects[PBEffects::SpecialUsage]
        user.lastMoveUsedSketch=thismove.id if user.effects[PBEffects::TwoTurnAttack]==0
        user.lastRegularMoveUsed=thismove.id
      end
      @battle.lastMoveUsed=thismove.id
      @battle.lastMoveUser=user.index
      return
    end
    # Primordial Sea, Desolate Land
    if thismove.pbIsDamaging?
      case @battle.pbWeather
      when PBWeather::HEAVYRAIN
        if isConst?(thismove.pbType(thismove.type,user,nil),PBTypes,:FIRE)
          PBDebug.log("[Move failed] Primordial Sea's rain cancelled the Fire-type #{thismove.name}")
          @battle.pbDisplay(_INTL("The Fire-type attack fizzled out in the heavy rain!"))
          user.lastMoveUsed=thismove.id
          user.lastMoveUsedType=thismove.pbType(thismove.type,user,nil)
          if !turneffects[PBEffects::SpecialUsage]
            user.lastMoveUsedSketch=thismove.id if user.effects[PBEffects::TwoTurnAttack]==0
            user.lastRegularMoveUsed=thismove.id
          end
          @battle.lastMoveUsed=thismove.id
          @battle.lastMoveUser=user.index
          return
        end
      when PBWeather::HARSHSUN
        if isConst?(thismove.pbType(thismove.type,user,nil),PBTypes,:WATER)
          PBDebug.log("[Move failed] Desolate Land's sun cancelled the Water-type #{thismove.name}")
          @battle.pbDisplay(_INTL("The Water-type attack evaporated in the harsh sunlight!"))
          user.lastMoveUsed=thismove.id
          user.lastMoveUsedType=thismove.pbType(thismove.type,user,nil)
          if !turneffects[PBEffects::SpecialUsage]
            user.lastMoveUsedSketch=thismove.id if user.effects[PBEffects::TwoTurnAttack]==0
            user.lastRegularMoveUsed=thismove.id
          end
          @battle.lastMoveUsed=thismove.id
          @battle.lastMoveUser=user.index
          return
        end
      end
    end
    # Powder
    if user.effects[PBEffects::Powder] && isConst?(thismove.pbType(thismove.type,user,nil),PBTypes,:FIRE)
      PBDebug.log("[Lingering effect triggered] #{pbThis}'s Powder cancelled the Fire move")
      @battle.pbCommonAnimation("Powder",user,nil)
      @battle.pbDisplay(_INTL("When the flame touched the powder on the Pokémon, it exploded!"))
      user.pbReduceHP(1+(user.totalhp/4).floor) if !user.hasWorkingAbility(:MAGICGUARD)   
      user.lastMoveUsed=thismove.id
      user.lastMoveUsedType=thismove.pbType(thismove.type,user,nil)
      if !turneffects[PBEffects::SpecialUsage]
        user.lastMoveUsedSketch=thismove.id if user.effects[PBEffects::TwoTurnAttack]==0
        user.lastRegularMoveUsed=thismove.id
      end
      @battle.lastMoveUsed=thismove.id
      @battle.lastMoveUser=user.index
      user.pbFaint if user.fainted?
      pbEndTurn(choice)
      return
    end
    # Protean
    if user.hasWorkingAbility(:PROTEAN) &&
       thismove.function!=0xAE &&   # Mirror Move
       thismove.function!=0xAF &&   # Copycat
       thismove.function!=0xB0 &&   # Me First
       thismove.function!=0xB3 &&   # Nature Power
       thismove.function!=0xB4 &&   # Sleep Talk
       thismove.function!=0xB5 &&   # Assist
       thismove.function!=0xB6      # Metronome
      movetype=thismove.pbType(thismove.type,user,nil)
      if !user.pbHasType?(movetype)
        typename=PBTypes.getName(movetype)
        PBDebug.log("[Ability triggered] #{pbThis}'s Protean made it #{typename}-type")
        user.type1=movetype
        user.type2=movetype
        user.effects[PBEffects::Type3]=-1
        @battle.pbDisplay(_INTL("{1} transformed into the {2} type!",user.pbThis,typename))  
      end
    end
    # Try to use move against user if there aren't any targets
    if targets.length==0
      user=pbChangeUser(thismove,user)
      if thismove.target==PBTargets::SingleNonUser ||
         thismove.target==PBTargets::RandomOpposing ||
         thismove.target==PBTargets::AllOpposing ||
         thismove.target==PBTargets::AllNonUsers ||
         thismove.target==PBTargets::Partner ||
         thismove.target==PBTargets::UserOrPartner ||
         thismove.target==PBTargets::SingleOpposing ||
         thismove.target==PBTargets::OppositeOpposing
        @battle.pbDisplay(_INTL("But there was no target..."))
      else
        PBDebug.logonerr{
           thismove.pbEffect(user,nil)
        }
      end
    else
      # We have targets
      showanimation=true
      alltargets=[]
      for i in 0...targets.length
        alltargets.push(targets[i].index) if !targets.include?(targets[i].index)
      end
      # For each target in turn
      i=0; loop do break if i>=targets.length
        # Get next target
        userandtarget=[user,targets[i]]
        success=pbChangeTarget(thismove,userandtarget,targets)
        user=userandtarget[0]
        target=userandtarget[1]
        if i==0 && thismove.target==PBTargets::AllOpposing
          # Add target's partner to list of targets
          pbAddTarget(targets,target.pbPartner)
        end
        # If couldn't get the next target
        if !success
          i+=1
          next
        end
        # Get the number of hits
        numhits=thismove.pbNumHits(user)
        # Reset damage state, set Focus Band/Focus Sash to available
        target.damagestate.reset
        # Use move against the current target
        pbProcessMoveAgainstTarget(thismove,user,target,numhits,turneffects,false,alltargets,showanimation)
        showanimation=false
        i+=1
      end
    end
    # Pokémon switching caused by Roar, Whirlwind, Circle Throw, Dragon Tail, Red Card
    if !user.fainted?
      switched=[]
      for i in 0...4
        if @battle.battlers[i].effects[PBEffects::Roar]
          @battle.battlers[i].effects[PBEffects::Roar]=false
          @battle.battlers[i].effects[PBEffects::Uturn]=false
          next if @battle.battlers[i].fainted?
          next if !@battle.pbCanSwitch?(i,-1,false)
          choices=[]
          party=@battle.pbParty(i)
          for j in 0...party.length
            choices.push(j) if @battle.pbCanSwitchLax?(i,j,false)
          end
          if choices.length>0
            newpoke=choices[@battle.pbRandom(choices.length)]
            newpokename=newpoke
            if isConst?(party[newpoke].ability,PBAbilities,:ILLUSION)
              newpokename=pbGetLastPokeInTeam(i)
            end
            switched.push(i)
            @battle.battlers[i].pbResetForm
            @battle.pbRecallAndReplace(i,newpoke,newpokename,false,user.hasMoldBreaker)
            @battle.pbDisplay(_INTL("{1} was dragged out!",@battle.battlers[i].pbThis))
            @battle.choices[i]=[0,0,nil,-1]   # Replacement Pokémon does nothing this round
          end
        end
      end
      for i in @battle.pbPriority
        next if !switched.include?(i.index)
        i.pbAbilitiesOnSwitchIn(true)
      end
    end
    # Pokémon switching caused by U-Turn, Volt Switch, Eject Button
    switched=[]
    for i in 0...4
      if @battle.battlers[i].effects[PBEffects::Uturn]
        @battle.battlers[i].effects[PBEffects::Uturn]=false
        @battle.battlers[i].effects[PBEffects::Roar]=false
        if !@battle.battlers[i].fainted? && @battle.pbCanChooseNonActive?(i) &&
           !@battle.pbAllFainted?(@battle.pbOpposingParty(i))
          # TODO: Pursuit should go here, and negate this effect if it KO's attacker
          @battle.pbDisplay(_INTL("{1} went back to {2}!",@battle.battlers[i].pbThis,@battle.pbGetOwner(i).name))
          newpoke=0
          newpoke=@battle.pbSwitchInBetween(i,true,false)
          newpokename=newpoke
          if isConst?(@battle.pbParty(i)[newpoke].ability,PBAbilities,:ILLUSION)
            newpokename=pbGetLastPokeInTeam(i)
          end
          switched.push(i)
          @battle.battlers[i].pbResetForm
          @battle.pbRecallAndReplace(i,newpoke,newpokename,@battle.battlers[i].effects[PBEffects::BatonPass])
          @battle.choices[i]=[0,0,nil,-1]   # Replacement Pokémon does nothing this round
        end
      end
    end
    for i in @battle.pbPriority
      next if !switched.include?(i.index)
      i.pbAbilitiesOnSwitchIn(true)
    end
    # Baton Pass
    if user.effects[PBEffects::BatonPass]
      user.effects[PBEffects::BatonPass]=false
      if !user.fainted? && @battle.pbCanChooseNonActive?(user.index) &&
         !@battle.pbAllFainted?(@battle.pbParty(user.index))
        newpoke=0
        newpoke=@battle.pbSwitchInBetween(user.index,true,false)
        newpokename=newpoke
        if isConst?(@battle.pbParty(user.index)[newpoke].ability,PBAbilities,:ILLUSION)
          newpokename=pbGetLastPokeInTeam(user.index)
        end
        user.pbResetForm
        @battle.pbRecallAndReplace(user.index,newpoke,newpokename,true)
        @battle.choices[user.index]=[0,0,nil,-1]   # Replacement Pokémon does nothing this round
        user.pbAbilitiesOnSwitchIn(true)
      end
    end
    # Record move as having been used
    user.lastMoveUsed=thismove.id
    user.lastMoveUsedType=thismove.pbType(thismove.type,user,nil)
    if !turneffects[PBEffects::SpecialUsage]
      user.lastMoveUsedSketch=thismove.id if user.effects[PBEffects::TwoTurnAttack]==0
      user.lastRegularMoveUsed=thismove.id
      user.movesUsed.push(thismove.id) if !user.movesUsed.include?(thismove.id) # For Last Resort
    end
    @battle.lastMoveUsed=thismove.id
    @battle.lastMoveUser=user.index
    # Gain Exp
    @battle.pbGainEXP
    # Battle Arena only - update skills
    for i in 0...4
      @battle.successStates[i].updateSkill
    end
    # End of move usage
    pbEndTurn(choice)
    @battle.pbJudge #    @battle.pbSwitch
    return
  end

  def pbCancelMoves
    # If failed pbTryUseMove or have already used Pursuit to chase a switching foe
    # Cancel multi-turn attacks (note: Hyper Beam effect is not canceled here)
    @effects[PBEffects::TwoTurnAttack]=0 if @effects[PBEffects::TwoTurnAttack]>0
    @effects[PBEffects::Outrage]=0
    @effects[PBEffects::Rollout]=0
    @effects[PBEffects::Uproar]=0
    @effects[PBEffects::Bide]=0
    @currentMove=0
    # Reset counters for moves which increase them when used in succession
    @effects[PBEffects::FuryCutter]=0
    PBDebug.log("Cancelled using the move")
  end

################################################################################
# Turn processing
################################################################################
  def pbBeginTurn(choice)
    # Cancel some lingering effects which only apply until the user next moves
    @effects[PBEffects::DestinyBond]=false
    @effects[PBEffects::Grudge]=false
    # Reset Parental Bond's count
    @effects[PBEffects::ParentalBond]=0
    # Encore's effect ends if the encored move is no longer available
    if @effects[PBEffects::Encore]>0 &&
       @moves[@effects[PBEffects::EncoreIndex]].id!=@effects[PBEffects::EncoreMove]
      PBDebug.log("Resetting Encore effect")
      @effects[PBEffects::Encore]=0
      @effects[PBEffects::EncoreIndex]=0
      @effects[PBEffects::EncoreMove]=0
    end
    # Wake up in an uproar
    if self.status==PBStatuses::SLEEP && !self.hasWorkingAbility(:SOUNDPROOF)
      for i in 0...4
        if @battle.battlers[i].effects[PBEffects::Uproar]>0
          pbCureStatus(false)
          @battle.pbDisplay(_INTL("{1} woke up in the uproar!",pbThis))
        end
      end
    end
  end

  def pbEndTurn(choice)
    # True end(?)
    if @effects[PBEffects::ChoiceBand]<0 && @lastMoveUsed>=0 && !fainted? && 
       (self.hasWorkingItem(:CHOICEBAND) ||
       self.hasWorkingItem(:CHOICESPECS) ||
       self.hasWorkingItem(:CHOICESCARF))
      @effects[PBEffects::ChoiceBand]=@lastMoveUsed
    end
    @battle.pbPrimordialWeather
    for i in 0...4
      @battle.battlers[i].pbBerryCureCheck
    end
    for i in 0...4
      @battle.battlers[i].pbAbilityCureCheck
    end
    for i in 0...4
      @battle.battlers[i].pbAbilitiesOnSwitchIn(false)
    end
    for i in 0...4
      @battle.battlers[i].pbCheckForm
    end
  end

  def pbProcessTurn(choice)
    # Can't use a move if fainted
    return false if fainted?
    # Wild roaming Pokémon always flee if possible
    if !@battle.opponent && @battle.pbIsOpposing?(self.index) &&
       @battle.rules["alwaysflee"] && @battle.pbCanRun?(self.index)
      pbBeginTurn(choice)
      @battle.pbDisplay(_INTL("{1} fled!",self.pbThis))
      @battle.decision=3
      pbEndTurn(choice)
      PBDebug.log("[Escape] #{pbThis} fled")
      return true
    end
    # If this battler's action for this round wasn't "use a move"
    if choice[0]!=1
      # Clean up effects that end at battler's turn
      pbBeginTurn(choice)
      pbEndTurn(choice)
      return false
    end
    # Turn is skipped if Pursuit was used during switch
    if @effects[PBEffects::Pursuit]
      @effects[PBEffects::Pursuit]=false
      pbCancelMoves
      pbEndTurn(choice)
      @battle.pbJudge #      @battle.pbSwitch
      return false
    end
    # Use the move
#   @battle.pbDisplayPaused("Before: [#{@lastMoveUsedSketch},#{@lastMoveUsed}]")
    PBDebug.log("#{pbThis} used #{choice[2].name}")
    PBDebug.logonerr{
       pbUseMove(choice,choice[2]==@battle.struggle)
    }
#   @battle.pbDisplayPaused("After: [#{@lastMoveUsedSketch},#{@lastMoveUsed}]")
    return true
  end
end