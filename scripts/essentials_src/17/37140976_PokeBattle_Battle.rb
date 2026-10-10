# Results of battle:
#    0 - Undecided or aborted
#    1 - Player won
#    2 - Player lost
#    3 - Player or wild Pokémon ran from battle, or player forfeited the match
#    4 - Wild Pokémon was caught
#    5 - Draw

################################################################################
# Catching and storing Pokémon.
################################################################################
module PokeBattle_BattleCommon
  def pbStorePokemon(pokemon)
    if !(pokemon.isShadow? rescue false)
      if pbDisplayConfirm(_INTL("Would you like to give a nickname to {1}?",pokemon.name))
        species=PBSpecies.getName(pokemon.species)
        nickname=@scene.pbNameEntry(_INTL("{1}'s nickname?",species),pokemon)
        pokemon.name=nickname if nickname!=""
      end
    end
    oldcurbox=@peer.pbCurrentBox()
    storedbox=@peer.pbStorePokemon(self.pbPlayer,pokemon)
    creator=@peer.pbGetStorageCreator()
    return if storedbox<0
    curboxname=@peer.pbBoxName(oldcurbox)
    boxname=@peer.pbBoxName(storedbox)
    if storedbox!=oldcurbox
      if creator
        pbDisplayPaused(_INTL("Box \"{1}\" on {2}'s PC was full.",curboxname,creator))
      else
        pbDisplayPaused(_INTL("Box \"{1}\" on someone's PC was full.",curboxname))
      end
      pbDisplayPaused(_INTL("{1} was transferred to box \"{2}\".",pokemon.name,boxname))
    else
      if creator
        pbDisplayPaused(_INTL("{1} was transferred to {2}'s PC.",pokemon.name,creator))
      else
        pbDisplayPaused(_INTL("{1} was transferred to someone's PC.",pokemon.name))
      end
      pbDisplayPaused(_INTL("It was stored in box \"{1}\".",boxname))
    end
  end

  def pbThrowPokeBall(idxPokemon,ball,rareness=nil,showplayer=false)
    itemname=PBItems.getName(ball)
    battler=nil
    if pbIsOpposing?(idxPokemon)
      battler=self.battlers[idxPokemon]
    else
      battler=self.battlers[idxPokemon].pbOppositeOpposing
    end
    if battler.fainted?
      battler=battler.pbPartner
    end
    pbDisplayBrief(_INTL("{1} threw one {2}!",self.pbPlayer.name,itemname))
    if battler.fainted?
      pbDisplay(_INTL("But there was no target..."))
      return
    end
    if @opponent && (!pbIsSnagBall?(ball) || !battler.isShadow?)
      @scene.pbThrowAndDeflect(ball,1)
      pbDisplay(_INTL("The Trainer blocked the Ball!\nDon't be a thief!"))
    else
      pokemon=battler.pokemon
      species=pokemon.species
      if $DEBUG && Input.press?(Input::CTRL)
        shakes=4
      else
        if !rareness
          dexdata=pbOpenDexData
          pbDexDataOffset(dexdata,pokemon.fSpecies,16)
          rareness=dexdata.fgetb # Get rareness from dexdata file
          dexdata.close
        end
        a=battler.totalhp
        b=battler.hp
        rareness=BallHandlers.modifyCatchRate(ball,rareness,self,battler)
        x=(((a*3-b*2)*rareness)/(a*3)).floor
        if battler.status==PBStatuses::SLEEP || battler.status==PBStatuses::FROZEN
          x=(x*2.5).floor
        elsif battler.status!=0
          x=(x*1.5).floor
        end
        c=0
        if $Trainer
          if $Trainer.pokedexOwned>600
            c=(x*2.5/6).floor
          elsif $Trainer.pokedexOwned>450
            c=(x*2/6).floor
          elsif $Trainer.pokedexOwned>300
            c=(x*1.5/6).floor
          elsif $Trainer.pokedexOwned>150
            c=(x*1/6).floor
          elsif $Trainer.pokedexOwned>30
            c=(x*0.5/6).floor
          end
        end
        shakes=0; critical=false
        if x>255 || BallHandlers.isUnconditional?(ball,self,battler)
          shakes=4
        else
          x=1 if x<1
          y = ( 65536 / ((255.0/x)**0.1875) ).floor
          if USECRITICALCAPTURE && pbRandom(256)<c
            critical=true
            shakes=4 if pbRandom(65536)<y
          else
            shakes+=1 if pbRandom(65536)<y
            shakes+=1 if pbRandom(65536)<y && shakes==1
            shakes+=1 if pbRandom(65536)<y && shakes==2
            shakes+=1 if pbRandom(65536)<y && shakes==3
          end
        end
      end
      PBDebug.log("[Threw Poké Ball] #{itemname}, #{shakes} shakes (4=capture)")
      @scene.pbThrow(ball,shakes,critical,battler.index,showplayer)
      case shakes
      when 0
        pbDisplay(_INTL("Oh no! The Pokémon broke free!"))
        BallHandlers.onFailCatch(ball,self,battler)
      when 1
        pbDisplay(_INTL("Aww... It appeared to be caught!"))
        BallHandlers.onFailCatch(ball,self,battler)
      when 2
        pbDisplay(_INTL("Aargh! Almost had it!"))
        BallHandlers.onFailCatch(ball,self,battler)
      when 3
        pbDisplay(_INTL("Gah! It was so close, too!"))
        BallHandlers.onFailCatch(ball,self,battler)
      when 4
        pbDisplayBrief(_INTL("Gotcha! {1} was caught!",pokemon.name))
        @scene.pbThrowSuccess
        if pbIsSnagBall?(ball) && @opponent
          pbRemoveFromParty(battler.index,battler.pokemonIndex)
          battler.pbReset
          battler.participants=[]
        else
          @decision=4
        end
        if pbIsSnagBall?(ball)
          pokemon.ot=self.pbPlayer.name
          pokemon.trainerID=self.pbPlayer.id
        end
        BallHandlers.onCatch(ball,self,pokemon)
        pokemon.ballused=pbGetBallType(ball)
        ((pokemon.makeUnmega if pokemon.isMega?) rescue nil)
        pokemon.makeUnprimal rescue nil
        pokemon.pbRecordFirstMoves
        if GAINEXPFORCAPTURE
          battler.captured=true
          pbGainEXP
          battler.captured=false
        end
        if !self.pbPlayer.hasOwned?(species)
          self.pbPlayer.setOwned(species)
          if $Trainer.pokedex
            pbDisplayPaused(_INTL("{1}'s data was added to the Pokédex.",pokemon.name))
            @scene.pbShowPokedex(species)
          end
        end
        pokemon.forcedForm = false if MultipleForms.hasFunction?(pokemon.species,"getForm")
        @scene.pbHideCaptureBall
        if pbIsSnagBall?(ball) && @opponent
          pokemon.pbUpdateShadowMoves rescue nil
          @snaggedpokemon.push(pokemon)
        else
          pbStorePokemon(pokemon)
        end
      end
    end
  end
end



################################################################################
# Main battle class.
################################################################################
class PokeBattle_Battle
  attr_reader(:scene)             # Scene object for this battle
  attr_accessor(:decision)        # Decision: 0=undecided; 1=win; 2=loss; 3=escaped; 4=caught
  attr_accessor(:internalbattle)  # Internal battle flag
  attr_accessor(:doublebattle)    # Double battle flag
  attr_accessor(:cantescape)      # True if player can't escape
  attr_accessor(:shiftStyle)      # Shift/Set "battle style" option
  attr_accessor(:battlescene)     # "Battle scene" option
  attr_accessor(:debug)           # Debug flag
  attr_reader(:player)            # Player trainer
  attr_reader(:opponent)          # Opponent trainer
  attr_reader(:party1)            # Player's Pokémon party
  attr_reader(:party2)            # Foe's Pokémon party
  attr_reader(:party1order)       # Order of Pokémon in the player's party
  attr_reader(:party2order)       # Order of Pokémon in the opponent's party
  attr_accessor(:fullparty1)      # True if player's party's max size is 6 instead of 3
  attr_accessor(:fullparty2)      # True if opponent's party's max size is 6 instead of 3
  attr_reader(:battlers)          # Currently active Pokémon
  attr_accessor(:items)           # Items held by opponents
  attr_reader(:sides)             # Effects common to each side of a battle
  attr_reader(:field)             # Effects common to the whole of a battle
  attr_accessor(:environment)     # Battle surroundings
  attr_accessor(:weather)         # Current weather, custom methods should use pbWeather instead
  attr_accessor(:weatherduration) # Duration of current weather, or -1 if indefinite
  attr_reader(:switching)         # True if during the switching phase of the round
  attr_reader(:futuresight)       # True if Future Sight is hitting
  attr_reader(:struggle)          # The Struggle move
  attr_accessor(:choices)         # Choices made by each Pokémon this round
  attr_reader(:successStates)     # Success states
  attr_accessor(:lastMoveUsed)    # Last move used
  attr_accessor(:lastMoveUser)    # Last move user
  attr_accessor(:megaEvolution)   # Battle index of each trainer's Pokémon to Mega Evolve
  attr_accessor(:amuletcoin)      # Whether Amulet Coin's effect applies
  attr_accessor(:extramoney)      # Money gained in battle by using Pay Day
  attr_accessor(:doublemoney)     # Whether Happy Hour's effect applies
  attr_accessor(:endspeech)       # Speech by opponent when player wins
  attr_accessor(:endspeech2)      # Speech by opponent when player wins
  attr_accessor(:endspeechwin)    # Speech by opponent when opponent wins
  attr_accessor(:endspeechwin2)   # Speech by opponent when opponent wins
  attr_accessor(:rules)
  attr_reader(:turncount)
  attr_accessor :controlPlayer
  include PokeBattle_BattleCommon
  
  MAXPARTYSIZE = 6

  class BattleAbortedException < Exception; end

  def pbAbort
    raise BattleAbortedException.new("Battle aborted")
  end

  def pbDebugUpdate
  end

  def pbRandom(x)
    return rand(x)
  end

  def pbAIRandom(x)
    return rand(x)
  end

################################################################################
# Initialise battle class.
################################################################################
  def initialize(scene,p1,p2,player,opponent)
    if p1.length==0
      raise ArgumentError.new(_INTL("Party 1 has no Pokémon."))
      return
    end
    if p2.length==0
      raise ArgumentError.new(_INTL("Party 2 has no Pokémon."))
      return
    end
    if p2.length>2 && !opponent
      raise ArgumentError.new(_INTL("Wild battles with more than two Pokémon are not allowed."))
      return
    end
    @scene           = scene
    @decision        = 0
    @internalbattle  = true
    @doublebattle    = false
    @cantescape      = false
    @shiftStyle      = true
    @battlescene     = true
    @debug           = false
    @debugupdate     = 0
    if opponent && player.is_a?(Array) && player.length==0
      player = player[0]
    end
    if opponent && opponent.is_a?(Array) && opponent.length==0
      opponent = opponent[0]
    end
    @player          = player                # PokeBattle_Trainer object
    @opponent        = opponent              # PokeBattle_Trainer object
    @party1          = p1
    @party2          = p2
    @party1order     = []
    for i in 0...12; @party1order.push(i); end
    @party2order     = []
    for i in 0...12; @party2order.push(i); end
    @fullparty1      = false
    @fullparty2      = false
    @battlers        = []
    @items           = nil
    @sides           = [PokeBattle_ActiveSide.new,   # Player's side
                        PokeBattle_ActiveSide.new]   # Foe's side
    @field           = PokeBattle_ActiveField.new    # Whole field (gravity/rooms)
    @environment     = PBEnvironment::None   # e.g. Tall grass, cave, still water
    @weather         = 0
    @weatherduration = 0
    @switching       = false
    @futuresight     = false
    @choices         = [ [0,0,nil,-1],[0,0,nil,-1],[0,0,nil,-1],[0,0,nil,-1] ]
    @successStates   = []
    for i in 0...4
      @successStates.push(PokeBattle_SuccessState.new)
    end
    @lastMoveUsed    = -1
    @lastMoveUser    = -1
    @nextPickupUse   = 0
    @megaEvolution   = []
    if @player.is_a?(Array)
      @megaEvolution[0]=[-1]*@player.length
    else
      @megaEvolution[0]=[-1]
    end
    if @opponent.is_a?(Array)
      @megaEvolution[1]=[-1]*@opponent.length
    else
      @megaEvolution[1]=[-1]
    end
    @amuletcoin      = false
    @extramoney      = 0
    @doublemoney     = false
    @endspeech       = ""
    @endspeech2      = ""
    @endspeechwin    = ""
    @endspeechwin2   = ""
    @rules           = {}
    @turncount       = 0
    @peer            = PokeBattle_BattlePeer.create()
    @priority        = []
    @usepriority     = false
    @snaggedpokemon  = []
    @runCommand      = 0
    if hasConst?(PBMoves,:STRUGGLE)
      @struggle = PokeBattle_Move.pbFromPBMove(self,PBMove.new(getConst(PBMoves,:STRUGGLE)))
    else
      @struggle = PokeBattle_Struggle.new(self,nil)
    end
    @struggle.pp     = -1
    for i in 0...4
      battlers[i] = PokeBattle_Battler.new(self,i)
    end
    for i in @party1
      next if !i
      i.itemRecycle = 0
      i.itemInitial = i.item
      i.belch       = false
    end
    for i in @party2
      next if !i
      i.itemRecycle = 0
      i.itemInitial = i.item
      i.belch       = false
    end
  end

################################################################################
# Info about battle.
################################################################################
  def pbDoubleBattleAllowed?
    return false if !@fullparty1 && @party1.length>MAXPARTYSIZE
    return false if !@fullparty2 && @party2.length>MAXPARTYSIZE
    _opponent=@opponent
    _player=@player
    # Wild battle
    if !_opponent
      if @party2.length==1
        return false
      elsif @party2.length==2
        return true
      else
        return false
      end
    # Trainer battle
    else
      if _opponent.is_a?(Array)
        if _opponent.length==1
          _opponent=_opponent[0]
        elsif _opponent.length!=2
          return false
        end
      end
      _player=_player
      if _player.is_a?(Array)
        if _player.length==1
          _player=_player[0]
        elsif _player.length!=2
          return false
        end
      end
      if _opponent.is_a?(Array)
        sendout1=pbFindNextUnfainted(@party2,0,pbSecondPartyBegin(1))
        sendout2=pbFindNextUnfainted(@party2,pbSecondPartyBegin(1))
        return false if sendout1<0 || sendout2<0
      else
        sendout1=pbFindNextUnfainted(@party2,0)
        sendout2=pbFindNextUnfainted(@party2,sendout1+1)
        return false if sendout1<0 || sendout2<0
      end
    end
    if _player.is_a?(Array)
      sendout1=pbFindNextUnfainted(@party1,0,pbSecondPartyBegin(0))
      sendout2=pbFindNextUnfainted(@party1,pbSecondPartyBegin(0))
      return false if sendout1<0 || sendout2<0
    else
      sendout1=pbFindNextUnfainted(@party1,0)
      sendout2=pbFindNextUnfainted(@party1,sendout1+1)
      return false if sendout1<0 || sendout2<0
    end
    return true
  end

  def pbWeather
    for i in 0...4
      if @battlers[i].hasWorkingAbility(:CLOUDNINE) ||
         @battlers[i].hasWorkingAbility(:AIRLOCK)
        return 0
      end
    end
    return @weather
  end

################################################################################
# Get battler info.
################################################################################
  def pbIsOpposing?(index)
    return (index%2)==1
  end

  def pbOwnedByPlayer?(index)
    return false if pbIsOpposing?(index)
    return false if @player.is_a?(Array) && index==2
    return true
  end

  def pbIsDoubleBattler?(index)
    return (index>=2)
  end

  # Only used for Wish
  def pbThisEx(battlerindex,pokemonindex)
    party=pbParty(battlerindex)
    if pbIsOpposing?(battlerindex)
      if @opponent
        return _INTL("The foe {1}",party[pokemonindex].name)
      else
        return _INTL("The wild {1}",party[pokemonindex].name)
      end
    else
      return party[pokemonindex].name
    end
  end

# Checks whether an item can be removed from a Pokémon.
  def pbIsUnlosableItem(pkmn,item)
    return true if pbIsMail?(item)
    return false if pkmn.effects[PBEffects::Transform]
    return true if pkmn.pokemon && pkmn.pokemon.getMegaForm(true)!=0 # Mega Stone
    if isConst?(pkmn.ability,PBAbilities,:MULTITYPE)
      plates=[:FISTPLATE,:SKYPLATE,:TOXICPLATE,:EARTHPLATE,:STONEPLATE,
              :INSECTPLATE,:SPOOKYPLATE,:IRONPLATE,:FLAMEPLATE,:SPLASHPLATE,
              :MEADOWPLATE,:ZAPPLATE,:MINDPLATE,:ICICLEPLATE,:DRACOPLATE,
              :DREADPLATE,:PIXIEPLATE]
      for i in plates
        return true if isConst?(item,PBItems,i)
      end
    end
    combos=[[:GIRATINA,:GRISEOUSORB],
            [:GENESECT,:BURNDRIVE],
            [:GENESECT,:CHILLDRIVE],
            [:GENESECT,:DOUSEDRIVE],
            [:GENESECT,:SHOCKDRIVE],
            # Primal Reversion stones
            [:KYOGRE,:BLUEORB],
            [:GROUDON,:REDORB]
           ]
    for i in combos
      if isConst?(pkmn.species,PBSpecies,i[0]) && isConst?(item,PBItems,i[1])
        return true
      end
    end
    return false
  end

  def pbCheckGlobalAbility(a)
    for i in 0...4 # in order from own first, opposing first, own second, opposing second
      if @battlers[i].hasWorkingAbility(a)
        return @battlers[i]
      end
    end
    return nil
  end

  def nextPickupUse
    @nextPickupUse+=1
    return @nextPickupUse
  end

################################################################################
# Player-related info.
################################################################################
  def pbPlayer
    if @player.is_a?(Array)
      return @player[0]
    else
      return @player
    end
  end

  def pbGetOwnerItems(battlerIndex)
    return [] if !@items
    if pbIsOpposing?(battlerIndex)
      if @opponent.is_a?(Array)
        return (battlerIndex==1) ? @items[0] : @items[1]
      else
        return @items
      end
    else
      return []
    end
  end

  def pbSetSeen(pokemon)
    if pokemon && @internalbattle
      self.pbPlayer.seen[pokemon.species]=true
      pbSeenForm(pokemon)
    end
  end

  def pbGetMegaRingName(battlerIndex)
    if pbBelongsToPlayer?(battlerIndex)
      for i in MEGARINGS
        next if !hasConst?(PBItems,i)
        return PBItems.getName(getConst(PBItems,i)) if $PokemonBag.pbHasItem?(i)
      end
    end
    # Add your own Mega objects for particular NPC trainers here
#    if isConst?(pbGetOwner(battlerIndex).trainertype,PBTrainers,:BUGCATCHER)
#      return _INTL("Mega Net")
#    end
    return _INTL("Mega Ring")
  end

  def pbHasMegaRing?(battlerIndex)
    return true if !pbBelongsToPlayer?(battlerIndex)
    for i in MEGARINGS
      next if !hasConst?(PBItems,i)
      return true if $PokemonBag.pbHasItem?(i)
    end
    return false
  end

################################################################################
# Get party info, manipulate parties.
################################################################################
  def pbPokemonCount(party)
    count=0
    for i in party
      next if !i
      count+=1 if i.hp>0 && !i.egg?
    end
    return count
  end

  def pbAllFainted?(party)
    pbPokemonCount(party)==0
  end

  def pbMaxLevel(party)
    lv=0
    for i in party
      next if !i
      lv=i.level if lv<i.level
    end
    return lv
  end

  def pbMaxLevelFromIndex(index)
    party=pbParty(index)
    owner=(pbIsOpposing?(index)) ? @opponent : @player
    maxlevel=0
    if owner.is_a?(Array)
      start=0
      limit=pbSecondPartyBegin(index)
      start=limit if pbIsDoubleBattler?(index)
      for i in start...start+limit
        next if !party[i]
        maxlevel=party[i].level if maxlevel<party[i].level
      end
    else
      for i in party
        next if !i
        maxlevel=i.level if maxlevel<i.level
      end
    end
    return maxlevel
  end

  def pbParty(index)
    return pbIsOpposing?(index) ? party2 : party1
  end

  def pbOpposingParty(index)
    return pbIsOpposing?(index) ? party1 : party2
  end

  def pbSecondPartyBegin(battlerIndex)
    if pbIsOpposing?(battlerIndex)
      return @fullparty2 ? 6 : 3
    else
      return @fullparty1 ? 6 : 3
    end
  end

  def pbPartyLength(battlerIndex)
    if pbIsOpposing?(battlerIndex)
      return (@opponent.is_a?(Array)) ? pbSecondPartyBegin(battlerIndex) : MAXPARTYSIZE
    else
      return @player.is_a?(Array) ? pbSecondPartyBegin(battlerIndex) : MAXPARTYSIZE
    end
  end

  def pbFindNextUnfainted(party,start,finish=-1)
    finish=party.length if finish<0
    for i in start...finish
      next if !party[i]
      return i if party[i].hp>0 && !party[i].egg?
    end
    return -1
  end

  def pbGetLastPokeInTeam(index)
    party=pbParty(index)
    partyorder=(!pbIsOpposing?(index)) ? @party1order : @party2order
    plength=pbPartyLength(index)
    pstart=pbGetOwnerIndex(index)*plength
    lastpoke=-1
    for i in pstart...pstart+plength
      p=party[partyorder[i]]
      next if !p || p.egg? || p.hp<=0
      lastpoke=partyorder[i]
    end
    return lastpoke
  end

  def pbFindPlayerBattler(pkmnIndex)
    battler=nil
    for k in 0...4
      if !pbIsOpposing?(k) && @battlers[k].pokemonIndex==pkmnIndex
        battler=@battlers[k]
        break
      end
    end
    return battler
  end

  def pbIsOwner?(battlerIndex,partyIndex)
    secondParty=pbSecondPartyBegin(battlerIndex)
    if !pbIsOpposing?(battlerIndex)
      return true if !@player || !@player.is_a?(Array)
      return (battlerIndex==0) ? partyIndex<secondParty : partyIndex>=secondParty
    else
      return true if !@opponent || !@opponent.is_a?(Array)
      return (battlerIndex==1) ? partyIndex<secondParty : partyIndex>=secondParty
    end
  end

  def pbGetOwner(battlerIndex)
    if pbIsOpposing?(battlerIndex)
      if @opponent.is_a?(Array)
        return (battlerIndex==1) ? @opponent[0] : @opponent[1]
      else
        return @opponent
      end
    else
      if @player.is_a?(Array)
        return (battlerIndex==0) ? @player[0] : @player[1]
      else
        return @player
      end
    end
  end

  def pbGetOwnerPartner(battlerIndex)
    if pbIsOpposing?(battlerIndex)
      if @opponent.is_a?(Array)
        return (battlerIndex==1) ? @opponent[1] : @opponent[0]
      else
        return @opponent
      end
    else
      if @player.is_a?(Array)
        return (battlerIndex==0) ? @player[1] : @player[0]
      else
        return @player
      end
    end
  end

  def pbGetOwnerIndex(battlerIndex)
    if pbIsOpposing?(battlerIndex)
      return (@opponent.is_a?(Array)) ? ((battlerIndex==1) ? 0 : 1) : 0
    else
      return (@player.is_a?(Array)) ? ((battlerIndex==0) ? 0 : 1) : 0
    end
  end

  def pbBelongsToPlayer?(battlerIndex)
    if @player.is_a?(Array) && @player.length>1
      return battlerIndex==0
    else
      return (battlerIndex%2)==0
    end
    return false
  end

  def pbPartyGetOwner(battlerIndex,partyIndex)
    secondParty=pbSecondPartyBegin(battlerIndex)
    if !pbIsOpposing?(battlerIndex)
      return @player if !@player || !@player.is_a?(Array)
      return (partyIndex<secondParty) ? @player[0] : @player[1]
    else
      return @opponent if !@opponent || !@opponent.is_a?(Array)
      return (partyIndex<secondParty) ? @opponent[0] : @opponent[1]
    end
  end

  def pbAddToPlayerParty(pokemon)
    party=pbParty(0)
    for i in 0...party.length
      party[i]=pokemon if pbIsOwner?(0,i) && !party[i]
    end
  end

  def pbRemoveFromParty(battlerIndex,partyIndex)
    party=pbParty(battlerIndex)
    side=(pbIsOpposing?(battlerIndex)) ? @opponent : @player
    order=(pbIsOpposing?(battlerIndex)) ? @party2order : @party1order
    secondpartybegin=pbSecondPartyBegin(battlerIndex)
    party[partyIndex]=nil
    if !side || !side.is_a?(Array) # Wild or single opponent
      party.compact!
      for i in partyIndex...party.length+1
        for j in 0...4
          next if !@battlers[j]
          if pbGetOwner(j)==side && @battlers[j].pokemonIndex==i
            @battlers[j].pokemonIndex-=1
            break
          end
        end
      end
      for i in 0...order.length
        order[i]=(i==partyIndex) ? order.length-1 : order[i]-1
      end
    else
      if partyIndex<secondpartybegin-1
        for i in partyIndex...secondpartybegin
          if i>=secondpartybegin-1
            party[i]=nil
          else
            party[i]=party[i+1]
          end
        end
        for i in 0...order.length
          next if order[i]>=secondpartybegin
          order[i]=(i==partyIndex) ? secondpartybegin-1 : order[i]-1
        end
      else
        for i in partyIndex...secondpartybegin+pbPartyLength(battlerIndex)
          if i>=party.length-1
            party[i]=nil
          else
            party[i]=party[i+1]
          end
        end
        for i in 0...order.length
          next if order[i]<secondpartybegin
          order[i]=(i==partyIndex) ? secondpartybegin+pbPartyLength(battlerIndex)-1 : order[i]-1
        end
      end
    end
  end

################################################################################
# Check whether actions can be taken.
################################################################################
  def pbCanShowCommands?(idxPokemon)
    thispkmn=@battlers[idxPokemon]
    return false if thispkmn.fainted?
    return false if thispkmn.effects[PBEffects::TwoTurnAttack]>0
    return false if thispkmn.effects[PBEffects::HyperBeam]>0
    return false if thispkmn.effects[PBEffects::Rollout]>0
    return false if thispkmn.effects[PBEffects::Outrage]>0
    return false if thispkmn.effects[PBEffects::Uproar]>0
    return false if thispkmn.effects[PBEffects::Bide]>0
    return true
  end

################################################################################
# Attacking.
################################################################################
  def pbCanShowFightMenu?(idxPokemon)
    thispkmn=@battlers[idxPokemon]
    if !pbCanShowCommands?(idxPokemon)
      return false
    end
    # No moves that can be chosen
    if !pbCanChooseMove?(idxPokemon,0,false) &&
       !pbCanChooseMove?(idxPokemon,1,false) &&
       !pbCanChooseMove?(idxPokemon,2,false) &&
       !pbCanChooseMove?(idxPokemon,3,false)
      return false
    end
    # Encore
    return false if thispkmn.effects[PBEffects::Encore]>0
    return true
  end

  def pbCanChooseMove?(idxPokemon,idxMove,showMessages,sleeptalk=false)
    thispkmn=@battlers[idxPokemon]
    thismove=thispkmn.moves[idxMove]
    opp1=thispkmn.pbOpposing1
    opp2=thispkmn.pbOpposing2
    if !thismove || thismove.id==0
      return false
    end
    if thismove.pp<=0 && thismove.totalpp>0 && !sleeptalk
      if showMessages
        pbDisplayPaused(_INTL("There's no PP left for this move!"))
      end
      return false
    end
    if thispkmn.hasWorkingItem(:ASSAULTVEST) && thismove.pbIsStatus?
      if showMessages
        pbDisplayPaused(_INTL("The effects of the {1} prevent status moves from being used!",
           PBItems.getName(thispkmn.item)))
      end
      return false
    end
    if thispkmn.effects[PBEffects::ChoiceBand]>=0 &&
       (thispkmn.hasWorkingItem(:CHOICEBAND) ||
       thispkmn.hasWorkingItem(:CHOICESPECS) ||
       thispkmn.hasWorkingItem(:CHOICESCARF))
      hasmove=false
      for i in 0...4
        if thispkmn.moves[i].id==thispkmn.effects[PBEffects::ChoiceBand]
          hasmove=true; break
        end
      end
      if hasmove && thismove.id!=thispkmn.effects[PBEffects::ChoiceBand]
        if showMessages
          pbDisplayPaused(_INTL("{1} allows the use of only {2}!",
             PBItems.getName(thispkmn.item),
             PBMoves.getName(thispkmn.effects[PBEffects::ChoiceBand])))
        end
        return false
      end
    end
    if opp1.effects[PBEffects::Imprison]
      if thismove.id==opp1.moves[0].id ||
         thismove.id==opp1.moves[1].id ||
         thismove.id==opp1.moves[2].id ||
         thismove.id==opp1.moves[3].id
        if showMessages
          pbDisplayPaused(_INTL("{1} can't use the sealed {2}!",thispkmn.pbThis,thismove.name))
        end
        #PBDebug.log("[CanChoose][#{opp1.pbThis} has: #{opp1.moves[0].name}, #{opp1.moves[1].name},#{opp1.moves[2].name},#{opp1.moves[3].name}]")
        return false
      end
    end
    if opp2.effects[PBEffects::Imprison]
      if thismove.id==opp2.moves[0].id ||
         thismove.id==opp2.moves[1].id ||
         thismove.id==opp2.moves[2].id ||
         thismove.id==opp2.moves[3].id
        if showMessages
          pbDisplayPaused(_INTL("{1} can't use the sealed {2}!",thispkmn.pbThis,thismove.name))
        end
        #PBDebug.log("[CanChoose][#{opp2.pbThis} has: #{opp2.moves[0].name}, #{opp2.moves[1].name},#{opp2.moves[2].name},#{opp2.moves[3].name}]")
        return false
      end
    end
    if thispkmn.effects[PBEffects::Taunt]>0 && thismove.basedamage==0
      if showMessages
        pbDisplayPaused(_INTL("{1} can't use {2} after the taunt!",thispkmn.pbThis,thismove.name))
      end
      return false
    end
    if thispkmn.effects[PBEffects::Torment]
      if thismove.id==thispkmn.lastMoveUsed
        if showMessages
          pbDisplayPaused(_INTL("{1} can't use the same move twice in a row due to the torment!",thispkmn.pbThis))
        end
        return false
      end
    end
    if thismove.id==thispkmn.effects[PBEffects::DisableMove] && !sleeptalk
      if showMessages
        pbDisplayPaused(_INTL("{1}'s {2} is disabled!",thispkmn.pbThis,thismove.name))
      end
      return false
    end
    if thismove.function==0x158 && # Belch
       (!thispkmn.pokemon || !thispkmn.pokemon.belch)
      if showMessages
        pbDisplayPaused(_INTL("{1} hasn't eaten any held berry, so it can't possibly belch!",thispkmn.pbThis))
      end
      return false
    end
    if thispkmn.effects[PBEffects::Encore]>0 && idxMove!=thispkmn.effects[PBEffects::EncoreIndex]
      return false
    end
    return true
  end

  def pbAutoChooseMove(idxPokemon,showMessages=true)
    thispkmn=@battlers[idxPokemon]
    if thispkmn.fainted?
      @choices[idxPokemon][0]=0
      @choices[idxPokemon][1]=0
      @choices[idxPokemon][2]=nil
      return
    end
    if thispkmn.effects[PBEffects::Encore]>0 && 
       pbCanChooseMove?(idxPokemon,thispkmn.effects[PBEffects::EncoreIndex],false)
      PBDebug.log("[Auto choosing Encore move] #{thispkmn.moves[thispkmn.effects[PBEffects::EncoreIndex]].name}")
      @choices[idxPokemon][0]=1    # "Use move"
      @choices[idxPokemon][1]=thispkmn.effects[PBEffects::EncoreIndex] # Index of move
      @choices[idxPokemon][2]=thispkmn.moves[thispkmn.effects[PBEffects::EncoreIndex]]
      @choices[idxPokemon][3]=-1   # No target chosen yet
      if @doublebattle
        thismove=thispkmn.moves[thispkmn.effects[PBEffects::EncoreIndex]]
        target=thispkmn.pbTarget(thismove)
        if target==PBTargets::SingleNonUser
          target=@scene.pbChooseTarget(idxPokemon,target)
          pbRegisterTarget(idxPokemon,target) if target>=0
        elsif target==PBTargets::UserOrPartner
          target=@scene.pbChooseTarget(idxPokemon,target)
          pbRegisterTarget(idxPokemon,target) if target>=0 && (target&1)==(idxPokemon&1)
        end
      end
    else
      if !pbIsOpposing?(idxPokemon)
        pbDisplayPaused(_INTL("{1} has no moves left!",thispkmn.name)) if showMessages
      end
      @choices[idxPokemon][0]=1           # "Use move"
      @choices[idxPokemon][1]=-1          # Index of move to be used
      @choices[idxPokemon][2]=@struggle   # Use Struggle
      @choices[idxPokemon][3]=-1          # No target chosen yet
    end
  end

  def pbRegisterMove(idxPokemon,idxMove,showMessages=true)
    thispkmn=@battlers[idxPokemon]
    thismove=thispkmn.moves[idxMove]
    return false if !pbCanChooseMove?(idxPokemon,idxMove,showMessages)
    @choices[idxPokemon][0]=1         # "Use move"
    @choices[idxPokemon][1]=idxMove   # Index of move to be used
    @choices[idxPokemon][2]=thismove  # PokeBattle_Move object of the move
    @choices[idxPokemon][3]=-1        # No target chosen yet
    return true
  end

  def pbChoseMove?(i,move)
    return false if @battlers[i].fainted?
    if @choices[i][0]==1 && @choices[i][1]>=0
      choice=@choices[i][1]
      return isConst?(@battlers[i].moves[choice].id,PBMoves,move)
    end
    return false
  end

  def pbChoseMoveFunctionCode?(i,code)
    return false if @battlers[i].fainted?
    if @choices[i][0]==1 && @choices[i][1]>=0
      choice=@choices[i][1]
      return @battlers[i].moves[choice].function==code
    end
    return false
  end

  def pbRegisterTarget(idxPokemon,idxTarget)
    @choices[idxPokemon][3]=idxTarget   # Set target of move
    return true
  end

  def pbPriority(ignorequickclaw=false,log=false)
    return @priority if @usepriority # use stored priority if round isn't over yet
    @priority.clear
    speeds=[]
    priorities=[]
    quickclaw=[]; lagging=[]
    minpri=0; maxpri=0
    temp=[]
    # Calculate each Pokémon's speed
    for i in 0...4
      speeds[i]=@battlers[i].pbSpeed
      quickclaw[i]=false
      lagging[i]=false
      if !ignorequickclaw && @choices[i][0]==1 # Chose to use a move
        if !quickclaw[i] && @battlers[i].hasWorkingItem(:CUSTAPBERRY) &&
           !@battlers[i].pbOpposing1.hasWorkingAbility(:UNNERVE) &&
           !@battlers[i].pbOpposing2.hasWorkingAbility(:UNNERVE)
          if (@battlers[i].hasWorkingAbility(:GLUTTONY) && @battlers[i].hp<=(@battlers[i].totalhp/2).floor) ||
             @battlers[i].hp<=(@battlers[i].totalhp/4).floor
            pbCommonAnimation("UseItem",@battlers[i],nil)
            quickclaw[i]=true
            pbDisplayBrief(_INTL("{1}'s {2} let it move first!",
               @battlers[i].pbThis,PBItems.getName(@battlers[i].item)))
            @battlers[i].pbConsumeItem
          end
        end
        if !quickclaw[i] && @battlers[i].hasWorkingItem(:QUICKCLAW)
          if pbRandom(10)<2
            pbCommonAnimation("UseItem",@battlers[i],nil)
            quickclaw[i]=true
            pbDisplayBrief(_INTL("{1}'s {2} let it move first!",
               @battlers[i].pbThis,PBItems.getName(@battlers[i].item)))
          end
        end
        if !quickclaw[i] &&
           (@battlers[i].hasWorkingAbility(:STALL) ||
           @battlers[i].hasWorkingItem(:LAGGINGTAIL) ||
           @battlers[i].hasWorkingItem(:FULLINCENSE))
          lagging[i]=true
        end
      end
    end
    # Calculate each Pokémon's priority bracket, and get the min/max priorities
    for i in 0...4
      # Assume that doing something other than using a move is priority 0
      pri=0
      if @choices[i][0]==1 # Chose to use a move
        pri=@choices[i][2].priority
        pri+=1 if @battlers[i].hasWorkingAbility(:PRANKSTER) &&
                  @choices[i][2].pbIsStatus?
        pri+=1 if @battlers[i].hasWorkingAbility(:GALEWINGS) &&
                  isConst?(@choices[i][2].type,PBTypes,:FLYING)
      end
      priorities[i]=pri
      if i==0
        minpri=pri
        maxpri=pri
      else
        minpri=pri if minpri>pri
        maxpri=pri if maxpri<pri
      end
    end
    # Find and order all moves with the same priority
    curpri=maxpri
    loop do
      temp.clear
      for j in 0...4
        temp.push(j) if priorities[j]==curpri
      end
      # Sort by speed
      if temp.length==1
        @priority[@priority.length]=@battlers[temp[0]]
      elsif temp.length>1
        n=temp.length
        for m in 0...temp.length-1
          for i in 1...temp.length
            # For each pair of battlers, rank the second compared to the first
            # -1 means rank higher, 0 means rank equal, 1 means rank lower
            cmp=0
            if quickclaw[temp[i]]
              cmp=-1
              if quickclaw[temp[i-1]]
                if speeds[temp[i]]==speeds[temp[i-1]]
                  cmp=0
                else
                  cmp=(speeds[temp[i]]>speeds[temp[i-1]]) ? -1 : 1
                end
              end
            elsif quickclaw[temp[i-1]]
              cmp=1
            elsif lagging[temp[i]]
              cmp=1
              if lagging[temp[i-1]]
                if speeds[temp[i]]==speeds[temp[i-1]]
                  cmp=0
                else
                  cmp=(speeds[temp[i]]>speeds[temp[i-1]]) ? 1 : -1
                end
              end
            elsif lagging[temp[i-1]]
              cmp=-1
            elsif speeds[temp[i]]!=speeds[temp[i-1]]
              if @field.effects[PBEffects::TrickRoom]>0
                cmp=(speeds[temp[i]]>speeds[temp[i-1]]) ? 1 : -1
              else
                cmp=(speeds[temp[i]]>speeds[temp[i-1]]) ? -1 : 1
              end
            end
            if cmp<0 || # Swap the pair according to the second battler's rank
               (cmp==0 && pbRandom(2)==0)
              swaptmp=temp[i]
              temp[i]=temp[i-1]
              temp[i-1]=swaptmp
            end
          end
        end
        # Battlers in this bracket are properly sorted, so add them to @priority
        for i in temp
          @priority[@priority.length]=@battlers[i]
        end
      end
      curpri-=1
      break if curpri<minpri
    end
    # Write the priority order to the debug log
    if log
      d="[Priority] "; comma=false
      for i in 0...4
        if @priority[i] && !@priority[i].fainted?
          d+=", " if comma
          d+="#{@priority[i].pbThis(comma)} (#{@priority[i].index})"; comma=true
        end
      end
      PBDebug.log(d)
    end
    @usepriority=true
    return @priority
  end

################################################################################
# Switching Pokémon.
################################################################################
  def pbCanSwitchLax?(idxPokemon,pkmnidxTo,showMessages)
    if pkmnidxTo>=0
      party=pbParty(idxPokemon)
      return false if pkmnidxTo>=party.length
      return false if !party[pkmnidxTo]
      if party[pkmnidxTo].egg?
        pbDisplayPaused(_INTL("An Egg can't battle!")) if showMessages 
        return false
      end
      if !pbIsOwner?(idxPokemon,pkmnidxTo)
        owner=pbPartyGetOwner(idxPokemon,pkmnidxTo)
        pbDisplayPaused(_INTL("You can't switch {1}'s Pokémon with one of yours!",owner.name)) if showMessages 
        return false
      end
      if party[pkmnidxTo].hp<=0
        pbDisplayPaused(_INTL("{1} has no energy left to battle!",party[pkmnidxTo].name)) if showMessages 
        return false
      end
      if @battlers[idxPokemon].pokemonIndex==pkmnidxTo ||
         @battlers[idxPokemon].pbPartner.pokemonIndex==pkmnidxTo
        pbDisplayPaused(_INTL("{1} is already in battle!",party[pkmnidxTo].name)) if showMessages 
        return false
      end
    end
    return true
  end

  def pbCanSwitch?(idxPokemon,pkmnidxTo,showMessages,ignoremeanlook=false)
    thispkmn=@battlers[idxPokemon]
    # Multi-Turn Attacks/Mean Look
    return false if !pbCanSwitchLax?(idxPokemon,pkmnidxTo,showMessages)
    isOpposing=pbIsOpposing?(idxPokemon)
    party=pbParty(idxPokemon)
    for i in 0...4
      next if isOpposing!=pbIsOpposing?(i)
      if choices[i][0]==2 && choices[i][1]==pkmnidxTo
        pbDisplayPaused(_INTL("{1} has already been selected.",party[pkmnidxTo].name)) if showMessages 
        return false
      end
    end
    return true if thispkmn.hasWorkingItem(:SHEDSHELL)
    return true if USENEWBATTLEMECHANICS && thispkmn.pbHasType?(:GHOST)
    if thispkmn.effects[PBEffects::MultiTurn]>0 ||
       (!ignoremeanlook && thispkmn.effects[PBEffects::MeanLook]>=0)
      pbDisplayPaused(_INTL("{1} can't be switched out!",thispkmn.pbThis)) if showMessages
      return false
    end
    if @field.effects[PBEffects::FairyLock]>0
      pbDisplayPaused(_INTL("{1} can't be switched out!",thispkmn.pbThis)) if showMessages
      return false
    end
    if thispkmn.effects[PBEffects::Ingrain]
      pbDisplayPaused(_INTL("{1} can't be switched out!",thispkmn.pbThis)) if showMessages
      return false
    end
    opp1=thispkmn.pbOpposing1
    opp2=thispkmn.pbOpposing2
    opp=nil
    if thispkmn.pbHasType?(:STEEL)
      opp=opp1 if opp1.hasWorkingAbility(:MAGNETPULL)
      opp=opp2 if opp2.hasWorkingAbility(:MAGNETPULL)
    end
    if !thispkmn.isAirborne?
      opp=opp1 if opp1.hasWorkingAbility(:ARENATRAP)
      opp=opp2 if opp2.hasWorkingAbility(:ARENATRAP)
    end
    if !thispkmn.hasWorkingAbility(:SHADOWTAG)
      opp=opp1 if opp1.hasWorkingAbility(:SHADOWTAG)
      opp=opp2 if opp2.hasWorkingAbility(:SHADOWTAG)
    end
    if opp
      abilityname=PBAbilities.getName(opp.ability)
      pbDisplayPaused(_INTL("{1}'s {2} prevents switching!",opp.pbThis,abilityname)) if showMessages
      return false
    end
    return true
  end

  def pbRegisterSwitch(idxPokemon,idxOther)
    return false if !pbCanSwitch?(idxPokemon,idxOther,false)
    @choices[idxPokemon][0]=2          # "Switch Pokémon"
    @choices[idxPokemon][1]=idxOther   # Index of other Pokémon to switch with
    @choices[idxPokemon][2]=nil
    side=(pbIsOpposing?(idxPokemon)) ? 1 : 0
    owner=pbGetOwnerIndex(idxPokemon)
    if @megaEvolution[side][owner]==idxPokemon
      @megaEvolution[side][owner]=-1
    end
    return true
  end

  def pbCanChooseNonActive?(index)
    party=pbParty(index)
    for i in 0...party.length
      return true if pbCanSwitchLax?(index,i,false)
    end
    return false
  end

  def pbSwitch(favorDraws=false)
    if !favorDraws
      return if @decision>0
    else
      return if @decision==5
    end
    pbJudge()
    return if @decision>0
    firstbattlerhp=@battlers[0].hp
    switched=[]
    for index in 0...4
      next if !@doublebattle && pbIsDoubleBattler?(index)
      next if @battlers[index] && !@battlers[index].fainted?
      next if !pbCanChooseNonActive?(index)
      if !pbOwnedByPlayer?(index)
        if !pbIsOpposing?(index) || (@opponent && pbIsOpposing?(index))
          newenemy=pbSwitchInBetween(index,false,false)
          newenemyname=newenemy
          if newenemy>=0 && isConst?(pbParty(index)[newenemy].ability,PBAbilities,:ILLUSION)
            newenemyname=pbGetLastPokeInTeam(index)
          end
          opponent=pbGetOwner(index)
          if !@doublebattle && firstbattlerhp>0 && @shiftStyle && @opponent &&
              @internalbattle && pbCanChooseNonActive?(0) && pbIsOpposing?(index) &&
              @battlers[0].effects[PBEffects::Outrage]==0
            pbDisplayPaused(_INTL("{1} is about to send in {2}.",opponent.fullname,pbParty(index)[newenemyname].name))
            if pbDisplayConfirm(_INTL("Will {1} change Pokémon?",self.pbPlayer.name))
              newpoke=pbSwitchPlayer(0,true,true)
              if newpoke>=0
                newpokename=newpoke
                if isConst?(@party1[newpoke].ability,PBAbilities,:ILLUSION)
                  newpokename=pbGetLastPokeInTeam(0)
                end
                pbDisplayBrief(_INTL("{1}, that's enough! Come back!",@battlers[0].name))
                pbRecallAndReplace(0,newpoke,newpokename)
                switched.push(0)
              end
            end
          end
          pbRecallAndReplace(index,newenemy,newenemyname,false,false)
          switched.push(index)
        end
      elsif @opponent
        newpoke=pbSwitchInBetween(index,true,false)
        newpokename=newpoke
        if isConst?(@party1[newpoke].ability,PBAbilities,:ILLUSION)
          newpokename=pbGetLastPokeInTeam(index)
        end
        pbRecallAndReplace(index,newpoke,newpokename)
        switched.push(index)
      else
        switch=false
        if !pbDisplayConfirm(_INTL("Use next Pokémon?")) 
          switch=(pbRun(index,true)<=0)
        else
          switch=true
        end
        if switch
          newpoke=pbSwitchInBetween(index,true,false)
          newpokename=newpoke
          if isConst?(@party1[newpoke].ability,PBAbilities,:ILLUSION)
            newpokename=pbGetLastPokeInTeam(index)
          end
          pbRecallAndReplace(index,newpoke,newpokename)
          switched.push(index)
        end
      end
    end
    if switched.length>0
      priority=pbPriority
      for i in priority
        i.pbAbilitiesOnSwitchIn(true) if switched.include?(i.index)
      end
    end
  end

  def pbSendOut(index,pokemon)
    pbSetSeen(pokemon)
    @peer.pbOnEnteringBattle(self,pokemon)
    if pbIsOpposing?(index)
      @scene.pbTrainerSendOut(index,pokemon)
    else
      @scene.pbSendOut(index,pokemon)
    end
    @scene.pbResetMoveIndex(index)
  end

  def pbReplace(index,newpoke,batonpass=false)
    party=pbParty(index)
    oldpoke=@battlers[index].pokemonIndex
    # Initialise the new Pokémon
    @battlers[index].pbInitialize(party[newpoke],newpoke,batonpass)
    # Reorder the party for this battle
    partyorder=(!pbIsOpposing?(index)) ? @party1order : @party2order
    bpo=-1; bpn=-1
    for i in 0...partyorder.length
      bpo=i if partyorder[i]==oldpoke
      bpn=i if partyorder[i]==newpoke
    end
    p=partyorder[bpo]; partyorder[bpo]=partyorder[bpn]; partyorder[bpn]=p
    # Send out the new Pokémon
    pbSendOut(index,party[newpoke])
    pbSetSeen(party[newpoke])
  end

  def pbRecallAndReplace(index,newpoke,newpokename=-1,batonpass=false,moldbreaker=false)
    @battlers[index].pbResetForm
    if !@battlers[index].fainted?
      @scene.pbRecall(index)
    end
    pbMessagesOnReplace(index,newpoke,newpokename)
    pbReplace(index,newpoke,batonpass)
    return pbOnActiveOne(@battlers[index],false,moldbreaker)
  end

  def pbMessagesOnReplace(index,newpoke,newpokename=-1)
    newpokename=newpoke if newpokename<0
    party=pbParty(index)
    if pbOwnedByPlayer?(index)
#     if !party[newpoke]
#       p [index,newpoke,party[newpoke],pbAllFainted?(party)]
#       PBDebug.log([index,newpoke,party[newpoke],"pbMOR"].inspect)
#       for i in 0...party.length
#         PBDebug.log([i,party[i].hp].inspect)
#       end
#       raise BattleAbortedException.new
#     end
      opposing=@battlers[index].pbOppositeOpposing
      if opposing.fainted? || opposing.hp==opposing.totalhp
        pbDisplayBrief(_INTL("Go! {1}!",party[newpokename].name))
      elsif opposing.hp>=(opposing.totalhp/2)
        pbDisplayBrief(_INTL("Do it! {1}!",party[newpokename].name))
      elsif opposing.hp>=(opposing.totalhp/4)
        pbDisplayBrief(_INTL("Go for it, {1}!",party[newpokename].name))
      else
        pbDisplayBrief(_INTL("Your opponent's weak!\nGet 'em, {1}!",party[newpokename].name))
      end
      PBDebug.log("[Send out Pokémon] Player sent out #{party[newpokename].name} in position #{index}")
    else
#     if !party[newpoke]
#       p [index,newpoke,party[newpoke],pbAllFainted?(party)]
#       PBDebug.log([index,newpoke,party[newpoke],"pbMOR"].inspect)
#       for i in 0...party.length
#         PBDebug.log([i,party[i].hp].inspect)
#       end
#       raise BattleAbortedException.new
#     end
      owner=pbGetOwner(index)
      pbDisplayBrief(_INTL("{1} sent\r\nout {2}!",owner.fullname,party[newpokename].name))
      PBDebug.log("[Send out Pokémon] Opponent sent out #{party[newpokename].name} in position #{index}")
    end
  end

  def pbSwitchInBetween(index,lax,cancancel)
    if !pbOwnedByPlayer?(index)
      return @scene.pbChooseNewEnemy(index,pbParty(index))
    else
      return pbSwitchPlayer(index,lax,cancancel)
    end
  end

  def pbSwitchPlayer(index,lax,cancancel)
    if @debug
      return @scene.pbChooseNewEnemy(index,pbParty(index))
    else
      return @scene.pbSwitch(index,lax,cancancel)
    end
  end

################################################################################
# Using an item.
################################################################################
# Uses an item on a Pokémon in the player's party.
  def pbUseItemOnPokemon(item,pkmnIndex,userPkmn,scene)
    pokemon=@party1[pkmnIndex]
    battler=nil
    name=pbGetOwner(userPkmn.index).fullname
    name=pbGetOwner(userPkmn.index).name if pbBelongsToPlayer?(userPkmn.index)
    pbDisplayBrief(_INTL("{1} used the\r\n{2}.",name,PBItems.getName(item)))
    PBDebug.log("[Use item] Player used #{PBItems.getName(item)} on #{pokemon.name}")
    ret=false
    if pokemon.egg?
      pbDisplay(_INTL("But it had no effect!"))
    else
      for i in 0...4
        if !pbIsOpposing?(i) && @battlers[i].pokemonIndex==pkmnIndex
          battler=@battlers[i]
        end
      end
      ret=ItemHandlers.triggerBattleUseOnPokemon(item,pokemon,battler,scene)
    end
    if !ret && pbBelongsToPlayer?(userPkmn.index)
      if $PokemonBag.pbCanStore?(item)
        $PokemonBag.pbStoreItem(item)
      else
        raise _INTL("Couldn't return unused item to Bag somehow.")
      end
    end
    return ret
  end

# Uses an item on an active Pokémon.
  def pbUseItemOnBattler(item,index,userPkmn,scene)
    PBDebug.log("[Use item] Player used #{PBItems.getName(item)} on #{@battlers[index].pbThis(true)}")
    ret=ItemHandlers.triggerBattleUseOnBattler(item,@battlers[index],scene)
    if !ret && pbBelongsToPlayer?(userPkmn.index)
      if $PokemonBag.pbCanStore?(item)
        $PokemonBag.pbStoreItem(item)
      else
        raise _INTL("Couldn't return unused item to Bag somehow.")
      end
    end
    return ret
  end

  def pbRegisterItem(idxPokemon,idxItem,idxTarget=nil)
    if idxTarget!=nil && idxTarget>=0
      for i in 0...4
        if !@battlers[i].pbIsOpposing?(idxPokemon) &&
           @battlers[i].pokemonIndex==idxTarget &&
           @battlers[i].effects[PBEffects::Embargo]>0
          pbDisplay(_INTL("Embargo's effect prevents the item's use on {1}!",@battlers[i].pbThis(true)))
          if pbBelongsToPlayer?(@battlers[i].index)
            if $PokemonBag.pbCanStore?(idxItem)
              $PokemonBag.pbStoreItem(idxItem)
            else
              raise _INTL("Couldn't return unused item to Bag somehow.")
            end
          end
          return false
        end
      end
    end
    if ItemHandlers.hasUseInBattle(idxItem)
      if idxPokemon==0 # Player's first Pokémon
        if ItemHandlers.triggerBattleUseOnBattler(idxItem,@battlers[idxPokemon],self)
          # Using Poké Balls or Poké Doll only
          ItemHandlers.triggerUseInBattle(idxItem,@battlers[idxPokemon],self)
          if @doublebattle
            @battlers[idxPokemon].pbPartner.effects[PBEffects::SkipTurn]=true
          end
        else
          if $PokemonBag.pbCanStore?(idxItem)
            $PokemonBag.pbStoreItem(idxItem)
          else
            raise _INTL("Couldn't return unusable item to Bag somehow.")
          end
          return false
        end
      else
        if ItemHandlers.triggerBattleUseOnBattler(idxItem,@battlers[idxPokemon],self)
          pbDisplay(_INTL("It's impossible to aim without being focused!"))
        end
        return false
      end
    end
    @choices[idxPokemon][0]=3         # "Use an item"
    @choices[idxPokemon][1]=idxItem   # ID of item to be used
    @choices[idxPokemon][2]=idxTarget # Index of Pokémon to use item on
    side=(pbIsOpposing?(idxPokemon)) ? 1 : 0
    owner=pbGetOwnerIndex(idxPokemon)
    if @megaEvolution[side][owner]==idxPokemon
      @megaEvolution[side][owner]=-1
    end
    return true
  end

  def pbEnemyUseItem(item,battler)
    return 0 if !@internalbattle
    items=pbGetOwnerItems(battler.index)
    return if !items
    opponent=pbGetOwner(battler.index)
    for i in 0...items.length
      if items[i]==item
        items.delete_at(i)
        break
      end
    end
    itemname=PBItems.getName(item)
    pbDisplayBrief(_INTL("{1} used the\r\n{2}!",opponent.fullname,itemname))
    PBDebug.log("[Use item] Opponent used #{itemname} on #{battler.pbThis(true)}")
    if isConst?(item,PBItems,:POTION)
      battler.pbRecoverHP(20,true)
      pbDisplay(_INTL("{1}'s HP was restored.",battler.pbThis))
    elsif isConst?(item,PBItems,:SUPERPOTION)
      battler.pbRecoverHP(50,true)
      pbDisplay(_INTL("{1}'s HP was restored.",battler.pbThis))
    elsif isConst?(item,PBItems,:HYPERPOTION)
      battler.pbRecoverHP(200,true)
      pbDisplay(_INTL("{1}'s HP was restored.",battler.pbThis))
    elsif isConst?(item,PBItems,:MAXPOTION)
      battler.pbRecoverHP(battler.totalhp-battler.hp,true)
      pbDisplay(_INTL("{1}'s HP was restored.",battler.pbThis))
    elsif isConst?(item,PBItems,:FULLRESTORE)
      fullhp=(battler.hp==battler.totalhp)
      battler.pbRecoverHP(battler.totalhp-battler.hp,true)
      battler.status=0; battler.statusCount=0
      battler.effects[PBEffects::Confusion]=0
      if fullhp
        pbDisplay(_INTL("{1} became healthy!",battler.pbThis))
      else
        pbDisplay(_INTL("{1}'s HP was restored.",battler.pbThis))
      end
    elsif isConst?(item,PBItems,:FULLHEAL)
      battler.status=0; battler.statusCount=0
      battler.effects[PBEffects::Confusion]=0
      pbDisplay(_INTL("{1} became healthy!",battler.pbThis))
    elsif isConst?(item,PBItems,:XATTACK)
      if battler.pbCanIncreaseStatStage?(PBStats::ATTACK,battler)
        battler.pbIncreaseStat(PBStats::ATTACK,1,battler,true)
      end
    elsif isConst?(item,PBItems,:XDEFEND)
      if battler.pbCanIncreaseStatStage?(PBStats::DEFENSE,battler)
        battler.pbIncreaseStat(PBStats::DEFENSE,1,battler,true)
      end
    elsif isConst?(item,PBItems,:XSPEED)
      if battler.pbCanIncreaseStatStage?(PBStats::SPEED,battler)
        battler.pbIncreaseStat(PBStats::SPEED,1,battler,true)
      end
    elsif isConst?(item,PBItems,:XSPECIAL)
      if battler.pbCanIncreaseStatStage?(PBStats::SPATK,battler)
        battler.pbIncreaseStat(PBStats::SPATK,1,battler,true)
      end
    elsif isConst?(item,PBItems,:XSPDEF)
      if battler.pbCanIncreaseStatStage?(PBStats::SPDEF,battler)
        battler.pbIncreaseStat(PBStats::SPDEF,1,battler,true)
      end
    elsif isConst?(item,PBItems,:XACCURACY)
      if battler.pbCanIncreaseStatStage?(PBStats::ACCURACY,battler)
        battler.pbIncreaseStat(PBStats::ACCURACY,1,battler,true)
      end
    end
  end

################################################################################
# Fleeing from battle.
################################################################################
  def pbCanRun?(idxPokemon)
    return false if @opponent
    return false if @cantescape && !pbIsOpposing?(idxPokemon)
    thispkmn=@battlers[idxPokemon]
    return true if thispkmn.pbHasType?(:GHOST) && USENEWBATTLEMECHANICS
    return true if thispkmn.hasWorkingItem(:SMOKEBALL)
    return true if thispkmn.hasWorkingAbility(:RUNAWAY)
    return pbCanSwitch?(idxPokemon,-1,false)
  end

  def pbRun(idxPokemon,duringBattle=false)
    thispkmn=@battlers[idxPokemon]
    if pbIsOpposing?(idxPokemon)
      return 0 if @opponent
      @choices[i][0]=5 # run
      @choices[i][1]=0 
      @choices[i][2]=nil
      return -1
    end
    if @opponent
      if $DEBUG && Input.press?(Input::CTRL)
        if pbDisplayConfirm(_INTL("Treat this battle as a win?"))
          @decision=1
          return 1
        elsif pbDisplayConfirm(_INTL("Treat this battle as a loss?"))
          @decision=2
          return 1
        end
      elsif @internalbattle
        pbDisplayPaused(_INTL("No! There's no running from a Trainer battle!"))
      elsif pbDisplayConfirm(_INTL("Would you like to forfeit the match and quit now?"))
        pbSEPlay("Battle flee")
        pbDisplay(_INTL("{1} forfeited the match!",self.pbPlayer.name))
        @decision=3
        return 1
      end
      return 0
    end
    if $DEBUG && Input.press?(Input::CTRL)
      pbSEPlay("Battle flee")
      pbDisplayPaused(_INTL("Got away safely!"))
      @decision=3
      return 1
    end
    if @cantescape
      pbDisplayPaused(_INTL("Can't escape!"))
      return 0
    end
    if thispkmn.pbHasType?(:GHOST) && USENEWBATTLEMECHANICS
      pbSEPlay("Battle flee")
      pbDisplayPaused(_INTL("Got away safely!"))
      @decision=3
      return 1
    end
    if thispkmn.hasWorkingAbility(:RUNAWAY)
      pbSEPlay("Battle flee")
      if duringBattle
        pbDisplayPaused(_INTL("Got away safely!"))
      else
        pbDisplayPaused(_INTL("{1} escaped using Run Away!",thispkmn.pbThis))
      end
      @decision=3
      return 1
    end
    if thispkmn.hasWorkingItem(:SMOKEBALL)
      pbSEPlay("Battle flee")
      if duringBattle
        pbDisplayPaused(_INTL("Got away safely!"))
      else
        pbDisplayPaused(_INTL("{1} escaped using its {2}!",thispkmn.pbThis,PBItems.getName(thispkmn.item)))
      end
      @decision=3
      return 1
    end
    if !duringBattle && !pbCanSwitch?(idxPokemon,-1,false)
      pbDisplayPaused(_INTL("Can't escape!"))
      return 0
    end
    # Note: not pbSpeed, because using unmodified Speed
    speedPlayer=@battlers[idxPokemon].speed
    opposing=@battlers[idxPokemon].pbOppositeOpposing
    opposing=opposing.pbPartner if opposing.fainted?
    if !opposing.fainted?
      speedEnemy=opposing.speed
      if speedPlayer>speedEnemy
        rate=256
      else
        speedEnemy=1 if speedEnemy<=0
        rate=speedPlayer*128/speedEnemy
        rate+=@runCommand*30
        rate&=0xFF
      end
    else
      rate=256
    end
    ret=1
    if pbAIRandom(256)<rate
      pbSEPlay("Battle flee")
      pbDisplayPaused(_INTL("Got away safely!"))
      @decision=3
    else
      pbDisplayPaused(_INTL("Can't escape!"))
      ret=-1
    end
    @runCommand+=1 if !duringBattle
    return ret
  end

################################################################################
# Mega Evolve battler.
################################################################################
  def pbCanMegaEvolve?(index)
    return false if $game_switches[NO_MEGA_EVOLUTION]
    return false if !@battlers[index].hasMega?
    return false if pbIsOpposing?(index) && !@opponent
    return true if $DEBUG && Input.press?(Input::CTRL)
    return false if !pbHasMegaRing?(index)
    side=(pbIsOpposing?(index)) ? 1 : 0
    owner=pbGetOwnerIndex(index)
    return false if @megaEvolution[side][owner]!=-1
    return false if @battlers[index].effects[PBEffects::SkyDrop]
    return true
  end

  def pbRegisterMegaEvolution(index)
    side=(pbIsOpposing?(index)) ? 1 : 0
    owner=pbGetOwnerIndex(index)
    @megaEvolution[side][owner]=index
  end

  def pbMegaEvolve(index)
    return if !@battlers[index] || !@battlers[index].pokemon
    return if !(@battlers[index].hasMega? rescue false)
    return if (@battlers[index].isMega? rescue true)
    ownername=pbGetOwner(index).fullname
    ownername=pbGetOwner(index).name if pbBelongsToPlayer?(index)
    case (@battlers[index].pokemon.megaMessage rescue 0)
    when 1 # Rayquaza
      pbDisplay(_INTL("{1}'s fervent wish has reached {2}!",ownername,@battlers[index].pbThis))
    else
      pbDisplay(_INTL("{1}'s {2} is reacting to {3}'s {4}!",
         @battlers[index].pbThis,PBItems.getName(@battlers[index].item),
         ownername,pbGetMegaRingName(index)))
    end
    pbCommonAnimation("MegaEvolution",@battlers[index],nil)
    @battlers[index].pokemon.makeMega
    @battlers[index].form=@battlers[index].pokemon.form
    @battlers[index].pbUpdate(true)
    @scene.pbChangePokemon(@battlers[index],@battlers[index].pokemon)
    pbCommonAnimation("MegaEvolution2",@battlers[index],nil)
    meganame=(@battlers[index].pokemon.megaName rescue nil)
    if !meganame || meganame==""
      meganame=_INTL("Mega {1}",PBSpecies.getName(@battlers[index].pokemon.species))
    end
    pbDisplay(_INTL("{1} has Mega Evolved into {2}!",@battlers[index].pbThis,meganame))
    PBDebug.log("[Mega Evolution] #{@battlers[index].pbThis} became #{meganame}")
    side=(pbIsOpposing?(index)) ? 1 : 0
    owner=pbGetOwnerIndex(index)
    @megaEvolution[side][owner]=-2
  end

################################################################################
# Primal Revert battler.
################################################################################
  def pbPrimalReversion(index)
    return if !@battlers[index] || !@battlers[index].pokemon
    return if !(@battlers[index].hasPrimal? rescue false)
    return if (@battlers[index].isPrimal? rescue true)
    if isConst?(@battlers[index].pokemon.species,PBSpecies,:KYOGRE)
      pbCommonAnimation("PrimalKyogre",@battlers[index],nil)
    elsif isConst?(@battlers[index].pokemon.species,PBSpecies,:GROUDON)
      pbCommonAnimation("PrimalGroudon",@battlers[index],nil)
    end
    @battlers[index].pokemon.makePrimal
    @battlers[index].form=@battlers[index].pokemon.form
    @battlers[index].pbUpdate(true)
    @scene.pbChangePokemon(@battlers[index],@battlers[index].pokemon)
    if isConst?(@battlers[index].pokemon.species,PBSpecies,:KYOGRE)
      pbCommonAnimation("PrimalKyogre2",@battlers[index],nil)
    elsif isConst?(@battlers[index].pokemon.species,PBSpecies,:GROUDON)
      pbCommonAnimation("PrimalGroudon2",@battlers[index],nil)
    end
    pbDisplay(_INTL("{1}'s Primal Reversion!\nIt reverted to its primal form!",@battlers[index].pbThis))
    PBDebug.log("[Primal Reversion] #{@battlers[index].pbThis} Primal Reverted")
  end

################################################################################
# Call battler.
################################################################################
  def pbCall(index)
    owner=pbGetOwner(index)
    pbDisplay(_INTL("{1} called {2}!",owner.name,@battlers[index].name))
    pbDisplay(_INTL("{1}!",@battlers[index].name))
    PBDebug.log("[Call to Pokémon] #{owner.name} called to #{@battlers[index].pbThis(true)}")
    if @battlers[index].isShadow?
      if @battlers[index].inHyperMode?
        @battlers[index].pokemon.hypermode=false
        @battlers[index].pokemon.adjustHeart(-300)
        pbDisplay(_INTL("{1} came to its senses from the Trainer's call!",@battlers[index].pbThis))
      else
        pbDisplay(_INTL("But nothing happened!"))
      end
    elsif @battlers[index].status!=PBStatuses::SLEEP &&
          @battlers[index].pbCanIncreaseStatStage?(PBStats::ACCURACY,@battlers[index])
      @battlers[index].pbIncreaseStat(PBStats::ACCURACY,1,@battlers[index],true)
    else
      pbDisplay(_INTL("But nothing happened!"))
    end
  end

################################################################################
# Gaining Experience.
################################################################################
  def pbGainEXP
    return if !@internalbattle
    successbegin=true
    for i in 0...4 # Not ordered by priority
      if !@doublebattle && pbIsDoubleBattler?(i)
        @battlers[i].participants=[]
        next
      end
      if pbIsOpposing?(i) && @battlers[i].participants.length>0 &&
         (@battlers[i].fainted? || @battlers[i].captured)
        haveexpall=(hasConst?(PBItems,:EXPALL) && $PokemonBag.pbHasItem?(:EXPALL))
        # First count the number of participants
        partic=0
        expshare=0
        for j in @battlers[i].participants
          next if !@party1[j] || !pbIsOwner?(0,j)
          partic+=1 if @party1[j].hp>0 && !@party1[j].egg?
        end
        if !haveexpall
          for j in 0...@party1.length
            next if !@party1[j] || !pbIsOwner?(0,j)
            expshare+=1 if @party1[j].hp>0 && !@party1[j].egg? && 
                           (isConst?(@party1[j].item,PBItems,:EXPSHARE) ||
                           isConst?(@party1[j].itemInitial,PBItems,:EXPSHARE))
          end
        end
        # Now calculate EXP for the participants
        if partic>0 || expshare>0 || haveexpall
          if !@opponent && successbegin && pbAllFainted?(@party2)
            @scene.pbWildBattleSuccess
            successbegin=false
          end
          for j in 0...@party1.length
            next if !@party1[j] || !pbIsOwner?(0,j)
            next if @party1[j].hp<=0 || @party1[j].egg?
            haveexpshare=(isConst?(@party1[j].item,PBItems,:EXPSHARE) ||
                          isConst?(@party1[j].itemInitial,PBItems,:EXPSHARE))
            next if !haveexpshare && !@battlers[i].participants.include?(j)
            pbGainExpOne(j,@battlers[i],partic,expshare,haveexpall)
          end
          if haveexpall
            showmessage=true
            for j in 0...@party1.length
              next if !@party1[j] || !pbIsOwner?(0,j)
              next if @party1[j].hp<=0 || @party1[j].egg?
              next if isConst?(@party1[j].item,PBItems,:EXPSHARE) ||
                      isConst?(@party1[j].itemInitial,PBItems,:EXPSHARE)
              next if @battlers[i].participants.include?(j)
              pbDisplayPaused(_INTL("The rest of your team gained Exp. Points thanks to the {1}!",
                 PBItems.getName(getConst(PBItems,:EXPALL)))) if showmessage
              showmessage=false
              pbGainExpOne(j,@battlers[i],partic,expshare,haveexpall,false)
            end
          end
        end
        # Now clear the participants array
        @battlers[i].participants=[]
      end
    end
  end

  def pbGainExpOne(index,defeated,partic,expshare,haveexpall,showmessages=true)
    thispoke=@party1[index]
    # Original species, not current species
    level=defeated.level
    baseexp=defeated.pokemon.baseExp
    evyield=defeated.pokemon.evYield
    # Gain effort value points, using RS effort values
    totalev=0
    for k in 0...6
      totalev+=thispoke.ev[k]
    end
    for k in 0...6
      evgain=evyield[k]
      evgain*=2 if isConst?(thispoke.item,PBItems,:MACHOBRACE) ||
                   isConst?(thispoke.itemInitial,PBItems,:MACHOBRACE)
      case k
      when PBStats::HP
        evgain+=4 if isConst?(thispoke.item,PBItems,:POWERWEIGHT) ||
                     isConst?(thispoke.itemInitial,PBItems,:POWERWEIGHT)
      when PBStats::ATTACK
        evgain+=4 if isConst?(thispoke.item,PBItems,:POWERBRACER) ||
                     isConst?(thispoke.itemInitial,PBItems,:POWERBRACER)
      when PBStats::DEFENSE
        evgain+=4 if isConst?(thispoke.item,PBItems,:POWERBELT) ||
                     isConst?(thispoke.itemInitial,PBItems,:POWERBELT)
      when PBStats::SPATK
        evgain+=4 if isConst?(thispoke.item,PBItems,:POWERLENS) ||
                     isConst?(thispoke.itemInitial,PBItems,:POWERLENS)
      when PBStats::SPDEF
        evgain+=4 if isConst?(thispoke.item,PBItems,:POWERBAND) ||
                     isConst?(thispoke.itemInitial,PBItems,:POWERBAND)
      when PBStats::SPEED
        evgain+=4 if isConst?(thispoke.item,PBItems,:POWERANKLET) ||
                     isConst?(thispoke.itemInitial,PBItems,:POWERANKLET)
      end
      evgain*=2 if thispoke.pokerusStage>=1 # Infected or cured
      if evgain>0
        # Can't exceed overall limit
        evgain-=totalev+evgain-PokeBattle_Pokemon::EVLIMIT if totalev+evgain>PokeBattle_Pokemon::EVLIMIT
        # Can't exceed stat limit
        evgain-=thispoke.ev[k]+evgain-PokeBattle_Pokemon::EVSTATLIMIT if thispoke.ev[k]+evgain>PokeBattle_Pokemon::EVSTATLIMIT
        # Add EV gain
        thispoke.ev[k]+=evgain
        if thispoke.ev[k]>PokeBattle_Pokemon::EVSTATLIMIT
          print "Single-stat EV limit #{PokeBattle_Pokemon::EVSTATLIMIT} exceeded.\r\nStat: #{k}  EV gain: #{evgain}  EVs: #{thispoke.ev.inspect}"
          thispoke.ev[k]=PokeBattle_Pokemon::EVSTATLIMIT
        end
        totalev+=evgain
        if totalev>PokeBattle_Pokemon::EVLIMIT
          print "EV limit #{PokeBattle_Pokemon::EVLIMIT} exceeded.\r\nTotal EVs: #{totalev} EV gain: #{evgain}  EVs: #{thispoke.ev.inspect}"
        end
      end
    end
    # Gain experience
    ispartic=0
    ispartic=1 if defeated.participants.include?(index)
    haveexpshare=(isConst?(thispoke.item,PBItems,:EXPSHARE) ||
                  isConst?(thispoke.itemInitial,PBItems,:EXPSHARE)) ? 1 : 0
    exp=0
    if expshare>0
      if partic==0 # No participants, all Exp goes to Exp Share holders
        exp=(level*baseexp).floor
        exp=(exp/(NOSPLITEXP ? 1 : expshare)).floor*haveexpshare
      else
        if NOSPLITEXP
          exp=(level*baseexp).floor*ispartic
          exp=(level*baseexp/2).floor*haveexpshare if ispartic==0
        else
          exp=(level*baseexp/2).floor
          exp=(exp/partic).floor*ispartic + (exp/expshare).floor*haveexpshare
        end
      end
    elsif ispartic==1
      exp=(level*baseexp/(NOSPLITEXP ? 1 : partic)).floor
    elsif haveexpall
      exp=(level*baseexp/2).floor
    end
    return if exp<=0
    exp=(exp*3/2).floor if @opponent
    if USESCALEDEXPFORMULA
      exp=(exp/5).floor
      leveladjust=(2*level+10.0)/(level+thispoke.level+10.0)
      leveladjust=leveladjust**5
      leveladjust=Math.sqrt(leveladjust)
      exp=(exp*leveladjust).floor
      exp+=1 if ispartic>0 || haveexpshare>0
    else
      exp=(exp/7).floor
    end
    isOutsider=(thispoke.trainerID!=self.pbPlayer.id ||
               (thispoke.language!=0 && thispoke.language!=self.pbPlayer.language))
    if isOutsider
      if thispoke.language!=0 && thispoke.language!=self.pbPlayer.language
        exp=(exp*1.7).floor
      else
        exp=(exp*3/2).floor
      end
    end
    exp=(exp*3/2).floor if isConst?(thispoke.item,PBItems,:LUCKYEGG) ||
                           isConst?(thispoke.itemInitial,PBItems,:LUCKYEGG)
    growthrate=thispoke.growthrate
    newexp=PBExperience.pbAddExperience(thispoke.exp,exp,growthrate)
    exp=newexp-thispoke.exp
    if exp>0
      if showmessages
        if isOutsider
          pbDisplayPaused(_INTL("{1} gained a boosted {2} Exp. Points!",thispoke.name,exp))
        else
          pbDisplayPaused(_INTL("{1} gained {2} Exp. Points!",thispoke.name,exp))
        end
      end
      newlevel=PBExperience.pbGetLevelFromExperience(newexp,growthrate)
      tempexp=0
      curlevel=thispoke.level
      if newlevel<curlevel
        debuginfo="#{thispoke.name}: #{thispoke.level}/#{newlevel} | #{thispoke.exp}/#{newexp} | gain: #{exp}"
        raise RuntimeError.new(_INTL("The new level ({1}) is less than the Pokémon's\r\ncurrent level ({2}), which shouldn't happen.\r\n[Debug: {3}]",
                               newlevel,curlevel,debuginfo))
        return
      end
      if thispoke.respond_to?("isShadow?") && thispoke.isShadow?
        thispoke.exp+=exp
      else
        tempexp1=thispoke.exp
        tempexp2=0
        # Find battler
        battler=pbFindPlayerBattler(index)
        loop do
          # EXP Bar animation
          startexp=PBExperience.pbGetStartExperience(curlevel,growthrate)
          endexp=PBExperience.pbGetStartExperience(curlevel+1,growthrate)
          tempexp2=(endexp<newexp) ? endexp : newexp
          thispoke.exp=tempexp2
          @scene.pbEXPBar(thispoke,battler,startexp,endexp,tempexp1,tempexp2)
          tempexp1=tempexp2
          curlevel+=1
          if curlevel>newlevel
            thispoke.calcStats 
            battler.pbUpdate(false) if battler
            @scene.pbRefresh
            break
          end
          oldtotalhp=thispoke.totalhp
          oldattack=thispoke.attack
          olddefense=thispoke.defense
          oldspeed=thispoke.speed
          oldspatk=thispoke.spatk
          oldspdef=thispoke.spdef
          if battler && battler.pokemon && @internalbattle
            battler.pokemon.changeHappiness("levelup")
          end
          thispoke.calcStats
          battler.pbUpdate(false) if battler
          @scene.pbRefresh
          pbDisplayPaused(_INTL("{1} grew to Level {2}!",thispoke.name,curlevel))
          @scene.pbLevelUp(thispoke,battler,oldtotalhp,oldattack,
                           olddefense,oldspeed,oldspatk,oldspdef)
          # Finding all moves learned at this level
          movelist=thispoke.getMoveList
          for k in movelist
            if k[0]==thispoke.level   # Learned a new move
              pbLearnMove(index,k[1])
            end
          end
        end
      end
    end
  end

################################################################################
# Learning a move.
################################################################################
  def pbLearnMove(pkmnIndex,move)
    pokemon=@party1[pkmnIndex]
    return if !pokemon
    pkmnname=pokemon.name
    battler=pbFindPlayerBattler(pkmnIndex)
    movename=PBMoves.getName(move)
    for i in 0...4
      return if pokemon.moves[i].id==move
      if pokemon.moves[i].id==0
        pokemon.moves[i]=PBMove.new(move)
        battler.moves[i]=PokeBattle_Move.pbFromPBMove(self,pokemon.moves[i]) if battler
        pbDisplayPaused(_INTL("{1} learned {2}!",pkmnname,movename))
        PBDebug.log("[Learn move] #{pkmnname} learned #{movename}")
        return
      end
    end
    loop do
      pbDisplayPaused(_INTL("{1} is trying to learn {2}.",pkmnname,movename))
      pbDisplayPaused(_INTL("But {1} can't learn more than four moves.",pkmnname))
      if pbDisplayConfirm(_INTL("Delete a move to make room for {1}?",movename))
        pbDisplayPaused(_INTL("Which move should be forgotten?"))
        forgetmove=@scene.pbForgetMove(pokemon,move)
        if forgetmove>=0
          oldmovename=PBMoves.getName(pokemon.moves[forgetmove].id)
          pokemon.moves[forgetmove]=PBMove.new(move) # Replaces current/total PP
          battler.moves[forgetmove]=PokeBattle_Move.pbFromPBMove(self,pokemon.moves[forgetmove]) if battler
          pbDisplayPaused(_INTL("1,  2, and... ... ..."))
          pbDisplayPaused(_INTL("Poof!"))
          pbDisplayPaused(_INTL("{1} forgot {2}.",pkmnname,oldmovename))
          pbDisplayPaused(_INTL("And..."))
          pbDisplayPaused(_INTL("{1} learned {2}!",pkmnname,movename))
          PBDebug.log("[Learn move] #{pkmnname} forgot #{oldmovename} and learned #{movename}")
          return
        elsif pbDisplayConfirm(_INTL("Should {1} stop learning {2}?",pkmnname,movename))
          pbDisplayPaused(_INTL("{1} did not learn {2}.",pkmnname,movename))
          return
        end
      elsif pbDisplayConfirm(_INTL("Should {1} stop learning {2}?",pkmnname,movename))
        pbDisplayPaused(_INTL("{1} did not learn {2}.",pkmnname,movename))
        return
      end
    end
  end

################################################################################
# Abilities.
################################################################################
  def pbOnActiveAll
    for i in 0...4 # Currently unfainted participants will earn EXP even if they faint afterwards
      @battlers[i].pbUpdateParticipants if pbIsOpposing?(i)
      @amuletcoin=true if !pbIsOpposing?(i) &&
                          (isConst?(@battlers[i].item,PBItems,:AMULETCOIN) ||
                           isConst?(@battlers[i].item,PBItems,:LUCKINCENSE))
    end
    for i in 0...4
      if !@battlers[i].fainted?
        if @battlers[i].isShadow? && pbIsOpposing?(i)
          pbCommonAnimation("Shadow",@battlers[i],nil)
          pbDisplay(_INTL("Oh!\nA Shadow Pokémon!"))
        end
      end
    end
    # Weather-inducing abilities, Trace, Imposter, etc.
    @usepriority=false
    priority=pbPriority
    for i in priority
      i.pbAbilitiesOnSwitchIn(true)
    end
    # Check forms are correct
    for i in 0...4
      next if @battlers[i].fainted?
      @battlers[i].pbCheckForm
    end
  end

  def pbOnActiveOne(pkmn,onlyabilities=false,moldbreaker=false)
    return false if pkmn.fainted?
    if !onlyabilities
      for i in 0...4 # Currently unfainted participants will earn EXP even if they faint afterwards
        @battlers[i].pbUpdateParticipants if pbIsOpposing?(i)
        @amuletcoin=true if !pbIsOpposing?(i) &&
                            (isConst?(@battlers[i].item,PBItems,:AMULETCOIN) ||
                             isConst?(@battlers[i].item,PBItems,:LUCKINCENSE))
      end
      if pkmn.isShadow? && pbIsOpposing?(pkmn.index)
        pbCommonAnimation("Shadow",pkmn,nil)
        pbDisplay(_INTL("Oh!\nA Shadow Pokémon!"))
      end
      # Healing Wish
      if pkmn.effects[PBEffects::HealingWish]
        PBDebug.log("[Lingering effect triggered] #{pkmn.pbThis}'s Healing Wish")
        pbCommonAnimation("HealingWish",pkmn,nil)
        pbDisplayPaused(_INTL("The healing wish came true for {1}!",pkmn.pbThis(true)))
        pkmn.pbRecoverHP(pkmn.totalhp,true)
        pkmn.pbCureStatus(false)
        pkmn.effects[PBEffects::HealingWish]=false
      end
      # Lunar Dance
      if pkmn.effects[PBEffects::LunarDance]
        PBDebug.log("[Lingering effect triggered] #{pkmn.pbThis}'s Lunar Dance")
        pbCommonAnimation("LunarDance",pkmn,nil)
        pbDisplayPaused(_INTL("{1} became cloaked in mystical moonlight!",pkmn.pbThis))
        pkmn.pbRecoverHP(pkmn.totalhp,true)
        pkmn.pbCureStatus(false)
        for i in 0...4
          pkmn.moves[i].pp=pkmn.moves[i].totalpp
        end
        pkmn.effects[PBEffects::LunarDance]=false
      end
      # Spikes
      if pkmn.pbOwnSide.effects[PBEffects::Spikes]>0 && !pkmn.isAirborne?(moldbreaker)
        if !pkmn.hasWorkingAbility(:MAGICGUARD)
          PBDebug.log("[Entry hazard] #{pkmn.pbThis} triggered Spikes")
          spikesdiv=[8,6,4][pkmn.pbOwnSide.effects[PBEffects::Spikes]-1]
          @scene.pbDamageAnimation(pkmn,0)
          pkmn.pbReduceHP((pkmn.totalhp/spikesdiv).floor)
          pbDisplayPaused(_INTL("{1} is hurt by the spikes!",pkmn.pbThis))
        end
      end
      pkmn.pbFaint if pkmn.fainted?
      # Stealth Rock
      if pkmn.pbOwnSide.effects[PBEffects::StealthRock] && !pkmn.fainted?
        if !pkmn.hasWorkingAbility(:MAGICGUARD)
          atype=getConst(PBTypes,:ROCK) || 0
          eff=PBTypes.getCombinedEffectiveness(atype,pkmn.type1,pkmn.type2,pkmn.effects[PBEffects::Type3])
          if eff>0
            PBDebug.log("[Entry hazard] #{pkmn.pbThis} triggered Stealth Rock")
            @scene.pbDamageAnimation(pkmn,0)
            pkmn.pbReduceHP(((pkmn.totalhp*eff)/64).floor)
            pbDisplayPaused(_INTL("Pointed stones dug into {1}!",pkmn.pbThis))
          end
        end
      end
      pkmn.pbFaint if pkmn.fainted?
      # Toxic Spikes
      if pkmn.pbOwnSide.effects[PBEffects::ToxicSpikes]>0 && !pkmn.fainted?
        if !pkmn.isAirborne?(moldbreaker)
          if pkmn.pbHasType?(:POISON)
            PBDebug.log("[Entry hazard] #{pkmn.pbThis} absorbed Toxic Spikes")
            pkmn.pbOwnSide.effects[PBEffects::ToxicSpikes]=0
            pbDisplayPaused(_INTL("{1} absorbed the poison spikes!",pkmn.pbThis))
          elsif pkmn.pbCanPoisonSpikes?(moldbreaker)
            PBDebug.log("[Entry hazard] #{pkmn.pbThis} triggered Toxic Spikes")
            if pkmn.pbOwnSide.effects[PBEffects::ToxicSpikes]==2
              pkmn.pbPoison(nil,_INTL("{1} was badly poisoned by the poison spikes!",pkmn.pbThis,true))
            else
              pkmn.pbPoison(nil,_INTL("{1} was poisoned by the poison spikes!",pkmn.pbThis))
            end
          end
        end
      end
      # Sticky Web
      if pkmn.pbOwnSide.effects[PBEffects::StickyWeb] && !pkmn.fainted? &&
         !pkmn.isAirborne?(moldbreaker)
        if pkmn.pbCanReduceStatStage?(PBStats::SPEED,nil,false,nil,moldbreaker)
          PBDebug.log("[Entry hazard] #{pkmn.pbThis} triggered Sticky Web")
          pkmn.pbReduceStat(PBStats::SPEED,1,nil,false,nil,true,moldbreaker)
          pbDisplayPaused(_INTL("{1} was caught in a sticky web!",pkmn.pbThis))
        end
      end
    end
    pkmn.pbAbilityCureCheck
    if pkmn.fainted?
      pbGainEXP
      pbJudge #      pbSwitch
      return false
    end
#    pkmn.pbAbilitiesOnSwitchIn(true)
    if !onlyabilities
      pkmn.pbCheckForm
      pkmn.pbBerryCureCheck
    end
    return true
  end

  def pbPrimordialWeather
    # End Primordial Sea, Desolate Land, Delta Stream
    hasabil=false
    case @weather
    when PBWeather::HEAVYRAIN
      for i in 0...4
        if isConst?(@battlers[i].ability,PBAbilities,:PRIMORDIALSEA) &&
           !@battlers[i].fainted?
          hasabil=true; break
        end
        if !hasabil
          @weather=0
          pbDisplayBrief("The heavy rain has lifted!")
        end
      end
    when PBWeather::HARSHSUN
      for i in 0...4
        if isConst?(@battlers[i].ability,PBAbilities,:DESOLATELAND) &&
           !@battlers[i].fainted?
          hasabil=true; break
        end
        if !hasabil
          @weather=0
          pbDisplayBrief("The harsh sunlight faded!")
        end
      end
    when PBWeather::STRONGWINDS
      for i in 0...4
        if isConst?(@battlers[i].ability,PBAbilities,:DELTASTREAM) &&
           !@battlers[i].fainted?
          hasabil=true; break
        end
        if !hasabil
          @weather=0
          pbDisplayBrief("The mysterious air current has dissipated!")
        end
      end
    end
  end

################################################################################
# Judging.
################################################################################
  def pbJudgeCheckpoint(attacker,move=0)
  end

  def pbDecisionOnTime
    count1=0
    count2=0
    hptotal1=0
    hptotal2=0
    for i in @party1
      next if !i
      if i.hp>0 && !i.egg?
        count1+=1
        hptotal1+=i.hp
      end
    end
    for i in @party2
      next if !i
      if i.hp>0 && !i.egg?
        count2+=1
        hptotal2+=i.hp
      end
    end
    return 1 if count1>count2     # win
    return 2 if count1<count2     # loss
    return 1 if hptotal1>hptotal2 # win
    return 2 if hptotal1<hptotal2 # loss
    return 5                      # draw
  end

  def pbDecisionOnTime2
    count1=0
    count2=0
    hptotal1=0
    hptotal2=0
    for i in @party1
      next if !i
      if i.hp>0 && !i.egg?
        count1+=1
        hptotal1+=(i.hp*100/i.totalhp)
      end
    end
    hptotal1/=count1 if count1>0
    for i in @party2
      next if !i
      if i.hp>0 && !i.egg?
        count2+=1
        hptotal2+=(i.hp*100/i.totalhp)
      end
    end
    hptotal2/=count2 if count2>0
    return 1 if count1>count2     # win
    return 2 if count1<count2     # loss
    return 1 if hptotal1>hptotal2 # win
    return 2 if hptotal1<hptotal2 # loss
    return 5                      # draw
  end

  def pbDecisionOnDraw
    return 5 # draw
  end

  def pbJudge
#   PBDebug.log("[Counts: #{pbPokemonCount(@party1)}/#{pbPokemonCount(@party2)}]")
    if pbAllFainted?(@party1) && pbAllFainted?(@party2)
      @decision=pbDecisionOnDraw() # Draw
      return
    end
    if pbAllFainted?(@party1)
      @decision=2 # Loss
      return
    end
    if pbAllFainted?(@party2)
      @decision=1 # Win
      return
    end
  end

################################################################################
# Messages and animations.
################################################################################
  def pbDisplay(msg)
    @scene.pbDisplayMessage(msg)
  end

  def pbDisplayPaused(msg)
    @scene.pbDisplayPausedMessage(msg)
  end

  def pbDisplayBrief(msg)
    @scene.pbDisplayMessage(msg,true)
  end

  def pbDisplayConfirm(msg)
    @scene.pbDisplayConfirmMessage(msg)
  end

  def pbShowCommands(msg,commands,cancancel=true)
    @scene.pbShowCommands(msg,commands,cancancel)
  end

  def pbAnimation(move,attacker,opponent,hitnum=0)
    if @battlescene
      @scene.pbAnimation(move,attacker,opponent,hitnum)
    end
  end

  def pbCommonAnimation(name,attacker,opponent,hitnum=0)
    if @battlescene
      @scene.pbCommonAnimation(name,attacker,opponent,hitnum)
    end
  end

################################################################################
# Battle core.
################################################################################
  def pbStartBattle(canlose=false)
    PBDebug.log("")
    PBDebug.log("******************************************")
    begin
      pbStartBattleCore(canlose)
    rescue BattleAbortedException
      @decision=0
      @scene.pbEndBattle(@decision)
    end
    return @decision
  end

  def pbStartBattleCore(canlose)
    if !@fullparty1 && @party1.length>MAXPARTYSIZE
      raise ArgumentError.new(_INTL("Party 1 has more than {1} Pokémon.",MAXPARTYSIZE))
    end
    if !@fullparty2 && @party2.length>MAXPARTYSIZE
      raise ArgumentError.new(_INTL("Party 2 has more than {1} Pokémon.",MAXPARTYSIZE))
    end
#========================
# Initialize wild Pokémon
#========================
    if !@opponent
      if @party2.length==1
        if @doublebattle
          raise _INTL("Only two wild Pokémon are allowed in double battles")
        end
        wildpoke=@party2[0]
        @battlers[1].pbInitialize(wildpoke,0,false)
        @peer.pbOnEnteringBattle(self,wildpoke)
        pbSetSeen(wildpoke)
        @scene.pbStartBattle(self)
        pbDisplayPaused(_INTL("Wild {1} appeared!",wildpoke.name))
      elsif @party2.length==2
        if !@doublebattle
          raise _INTL("Only one wild Pokémon is allowed in single battles")
        end
        @battlers[1].pbInitialize(@party2[0],0,false)
        @battlers[3].pbInitialize(@party2[1],1,false)
        @peer.pbOnEnteringBattle(self,@party2[0])
        @peer.pbOnEnteringBattle(self,@party2[1])
        pbSetSeen(@party2[0])
        pbSetSeen(@party2[1])
        @scene.pbStartBattle(self)
        pbDisplayPaused(_INTL("Wild {1} and\r\n{2} appeared!",
           @party2[0].name,@party2[1].name))
      else
        raise _INTL("Only one or two wild Pokémon are allowed")
      end
#=======================================
# Initialize opponents in double battles
#=======================================
    elsif @doublebattle
      if @opponent.is_a?(Array)
        if @opponent.length==1
          @opponent=@opponent[0]
        elsif @opponent.length!=2
          raise _INTL("Opponents with zero or more than two people are not allowed")
        end
      end
      if @player.is_a?(Array)
        if @player.length==1
          @player=@player[0]
        elsif @player.length!=2
          raise _INTL("Player trainers with zero or more than two people are not allowed")
        end
      end
      @scene.pbStartBattle(self)
      if @opponent.is_a?(Array)
        pbDisplayPaused(_INTL("{1} and {2} want to battle!",@opponent[0].fullname,@opponent[1].fullname))
        sendout1=pbFindNextUnfainted(@party2,0,pbSecondPartyBegin(1))
        raise _INTL("Opponent 1 has no unfainted Pokémon") if sendout1<0
        sendout2=pbFindNextUnfainted(@party2,pbSecondPartyBegin(1))
        raise _INTL("Opponent 2 has no unfainted Pokémon") if sendout2<0
        @battlers[1].pbInitialize(@party2[sendout1],sendout1,false)
        pbDisplayBrief(_INTL("{1} sent\r\nout {2}!",@opponent[0].fullname,@battlers[1].name))
        pbSendOut(1,@party2[sendout1])
        @battlers[3].pbInitialize(@party2[sendout2],sendout2,false)
        pbDisplayBrief(_INTL("{1} sent\r\nout {2}!",@opponent[1].fullname,@battlers[3].name))
        pbSendOut(3,@party2[sendout2])
      else
        pbDisplayPaused(_INTL("{1}\r\nwould like to battle!",@opponent.fullname))
        sendout1=pbFindNextUnfainted(@party2,0)
        sendout2=pbFindNextUnfainted(@party2,sendout1+1)
        if sendout1<0 || sendout2<0
          raise _INTL("Opponent doesn't have two unfainted Pokémon")
        end
        @battlers[1].pbInitialize(@party2[sendout1],sendout1,false)
        @battlers[3].pbInitialize(@party2[sendout2],sendout2,false)
        pbDisplayBrief(_INTL("{1} sent\r\nout {2} and {3}!",
           @opponent.fullname,@battlers[1].name,@battlers[3].name))
        pbSendOut(1,@party2[sendout1])
        pbSendOut(3,@party2[sendout2])
      end
#======================================
# Initialize opponent in single battles
#======================================
    else
      sendout=pbFindNextUnfainted(@party2,0)
      raise _INTL("Trainer has no unfainted Pokémon") if sendout<0
      if @opponent.is_a?(Array)
        raise _INTL("Opponent trainer must be only one person in single battles") if @opponent.length!=1
        @opponent=@opponent[0]
      end
      if @player.is_a?(Array)
        raise _INTL("Player trainer must be only one person in single battles") if @player.length!=1
        @player=@player[0]
      end
      trainerpoke=@party2[sendout]
      @scene.pbStartBattle(self)
      pbDisplayPaused(_INTL("{1}\r\nwould like to battle!",@opponent.fullname))
      @battlers[1].pbInitialize(trainerpoke,sendout,false)
      pbDisplayBrief(_INTL("{1} sent\r\nout {2}!",@opponent.fullname,@battlers[1].name))
      pbSendOut(1,trainerpoke)
    end
#=====================================
# Initialize players in double battles
#=====================================
    if @doublebattle
      if @player.is_a?(Array)
        sendout1=pbFindNextUnfainted(@party1,0,pbSecondPartyBegin(0))
        raise _INTL("Player 1 has no unfainted Pokémon") if sendout1<0
        sendout2=pbFindNextUnfainted(@party1,pbSecondPartyBegin(0))
        raise _INTL("Player 2 has no unfainted Pokémon") if sendout2<0
        @battlers[0].pbInitialize(@party1[sendout1],sendout1,false)
        @battlers[2].pbInitialize(@party1[sendout2],sendout2,false)
        pbDisplayBrief(_INTL("{1} sent\r\nout {2}! Go! {3}!",
           @player[1].fullname,@battlers[2].name,@battlers[0].name))
        pbSetSeen(@party1[sendout1])
        pbSetSeen(@party1[sendout2])
      else
        sendout1=pbFindNextUnfainted(@party1,0)
        sendout2=pbFindNextUnfainted(@party1,sendout1+1)
        if sendout1<0 || sendout2<0
          raise _INTL("Player doesn't have two unfainted Pokémon")
        end
        @battlers[0].pbInitialize(@party1[sendout1],sendout1,false)
        @battlers[2].pbInitialize(@party1[sendout2],sendout2,false)
        pbDisplayBrief(_INTL("Go! {1} and {2}!",@battlers[0].name,@battlers[2].name))
      end
      pbSendOut(0,@party1[sendout1])
      pbSendOut(2,@party1[sendout2])
#====================================
# Initialize player in single battles
#====================================
    else
      sendout=pbFindNextUnfainted(@party1,0)
      if sendout<0
        raise _INTL("Player has no unfainted Pokémon")
      end
      @battlers[0].pbInitialize(@party1[sendout],sendout,false)
      pbDisplayBrief(_INTL("Go! {1}!",@battlers[0].name))
      pbSendOut(0,@party1[sendout])
    end
#==================
# Initialize battle
#==================
    if @weather==PBWeather::SUNNYDAY
      pbCommonAnimation("Sunny",nil,nil)
      pbDisplay(_INTL("The sunlight is strong."))
    elsif @weather==PBWeather::RAINDANCE
      pbCommonAnimation("Rain",nil,nil)
      pbDisplay(_INTL("It is raining."))
    elsif @weather==PBWeather::SANDSTORM
      pbCommonAnimation("Sandstorm",nil,nil)
      pbDisplay(_INTL("A sandstorm is raging."))
    elsif @weather==PBWeather::HAIL
      pbCommonAnimation("Hail",nil,nil)
      pbDisplay(_INTL("Hail is falling."))
    elsif @weather==PBWeather::HEAVYRAIN
      pbCommonAnimation("HeavyRain",nil,nil)
      pbDisplay(_INTL("It is raining heavily."))
    elsif @weather==PBWeather::HARSHSUN
      pbCommonAnimation("HarshSun",nil,nil)
      pbDisplay(_INTL("The sunlight is extremely harsh."))
    elsif @weather==PBWeather::STRONGWINDS
      pbCommonAnimation("StrongWinds",nil,nil)
      pbDisplay(_INTL("The wind is strong."))
    end
    pbOnActiveAll   # Abilities
    @turncount=0
    loop do   # Now begin the battle loop
      PBDebug.log("")
      PBDebug.log("***Round #{@turncount+1}***")
      if @debug && @turncount>=100
        @decision=pbDecisionOnTime()
        PBDebug.log("")
        PBDebug.log("***Undecided after 100 rounds, aborting***")
        pbAbort
        break
      end
      PBDebug.logonerr{
         pbCommandPhase
      }
      break if @decision>0
      PBDebug.logonerr{
         pbAttackPhase
      }
      break if @decision>0
      PBDebug.logonerr{
         pbEndOfRoundPhase
      }
      break if @decision>0
      @turncount+=1
    end
    return pbEndOfBattle(canlose)
  end

################################################################################
# Command phase.
################################################################################
  def pbCommandMenu(i)
    return @scene.pbCommandMenu(i)
  end

  def pbItemMenu(i)
    return @scene.pbItemMenu(i)
  end

  def pbAutoFightMenu(i)
    return false
  end

  def pbCommandPhase
    @scene.pbBeginCommandPhase
#    @scene.pbResetCommandIndices
    for i in 0...4   # Reset choices if commands can be shown
      @battlers[i].effects[PBEffects::SkipTurn]=false
      if pbCanShowCommands?(i) || @battlers[i].fainted?
        @choices[i][0]=0
        @choices[i][1]=0
        @choices[i][2]=nil
        @choices[i][3]=-1
      else
        unless !@doublebattle && pbIsDoubleBattler?(i)
          PBDebug.log("[Reusing commands] #{@battlers[i].pbThis(true)}")
        end
      end
    end
    # Reset choices to perform Mega Evolution if it wasn't done somehow
    for i in 0...2
      for j in 0...@megaEvolution[i].length
        @megaEvolution[i][j]=-1 if @megaEvolution[i][j]>=0
      end
    end
    for i in 0...4
      break if @decision!=0
      next if @choices[i][0]!=0
      if !pbOwnedByPlayer?(i) || @controlPlayer
        if !@battlers[i].fainted? && pbCanShowCommands?(i)
          @scene.pbChooseEnemyCommand(i)
        end
      else
        commandDone=false
        commandEnd=false
        if pbCanShowCommands?(i)
          loop do
            cmd=pbCommandMenu(i)
            if cmd==0 # Fight
              if pbCanShowFightMenu?(i)
                commandDone=true if pbAutoFightMenu(i)
                until commandDone
                  index=@scene.pbFightMenu(i)
                  if index<0
                    side=(pbIsOpposing?(i)) ? 1 : 0
                    owner=pbGetOwnerIndex(i)
                    if @megaEvolution[side][owner]==i
                      @megaEvolution[side][owner]=-1
                    end
                    break
                  end
                  next if !pbRegisterMove(i,index)
                  if @doublebattle
                    thismove=@battlers[i].moves[index]
                    target=@battlers[i].pbTarget(thismove)
                    if target==PBTargets::SingleNonUser # single non-user
                      target=@scene.pbChooseTarget(i,target)
                      next if target<0
                      pbRegisterTarget(i,target)
                    elsif target==PBTargets::UserOrPartner # Acupressure
                      target=@scene.pbChooseTarget(i,target)
                      next if target<0 || (target&1)==1
                      pbRegisterTarget(i,target)
                    end
                  end
                  commandDone=true
                end
              else
                pbAutoChooseMove(i)
                commandDone=true
              end
            elsif cmd!=0 && @battlers[i].effects[PBEffects::SkyDrop]
              pbDisplay(_INTL("Sky Drop won't let {1} go!",@battlers[i].pbThis(true)))
            elsif cmd==1 # Bag
              if !@internalbattle
                if pbOwnedByPlayer?(i)
                  pbDisplay(_INTL("Items can't be used here."))
                end
              else
                item=pbItemMenu(i)
                if item[0]>0
                  if pbRegisterItem(i,item[0],item[1])
                    commandDone=true
                  end
                end
              end
            elsif cmd==2 # Pokémon
              pkmn=pbSwitchPlayer(i,false,true)
              if pkmn>=0
                commandDone=true if pbRegisterSwitch(i,pkmn)
              end
            elsif cmd==3   # Run
              run=pbRun(i) 
              if run>0
                commandDone=true
                return
              elsif run<0
                commandDone=true
                side=(pbIsOpposing?(i)) ? 1 : 0
                owner=pbGetOwnerIndex(i)
                if @megaEvolution[side][owner]==i
                  @megaEvolution[side][owner]=-1
                end
              end
            elsif cmd==4   # Call
              thispkmn=@battlers[i]
              @choices[i][0]=4   # "Call Pokémon"
              @choices[i][1]=0
              @choices[i][2]=nil
              side=(pbIsOpposing?(i)) ? 1 : 0
              owner=pbGetOwnerIndex(i)
              if @megaEvolution[side][owner]==i
                @megaEvolution[side][owner]=-1
              end
              commandDone=true
            elsif cmd==-1   # Go back to first battler's choice
              @megaEvolution[0][0]=-1 if @megaEvolution[0][0]>=0
              @megaEvolution[1][0]=-1 if @megaEvolution[1][0]>=0
              # Restore the item the player's first Pokémon was due to use
              if @choices[0][0]==3 && $PokemonBag && $PokemonBag.pbCanStore?(@choices[0][1])
                $PokemonBag.pbStoreItem(@choices[0][1])
              end
              pbCommandPhase
              return
            end
            break if commandDone
          end
        end
      end
    end
  end

################################################################################
# Attack phase.
################################################################################
  def pbAttackPhase
    @scene.pbBeginAttackPhase
    for i in 0...4
      @successStates[i].clear
      if @choices[i][0]!=1 && @choices[i][0]!=2
        @battlers[i].effects[PBEffects::DestinyBond]=false
        @battlers[i].effects[PBEffects::Grudge]=false
      end
      @battlers[i].turncount+=1 if !@battlers[i].fainted?
      @battlers[i].effects[PBEffects::Rage]=false if !pbChoseMove?(i,:RAGE)
    end
    # Calculate priority at this time
    @usepriority=false
    priority=pbPriority(false,true)
    # Mega Evolution
    megaevolved=[]
    for i in priority
      if @choices[i.index][0]==1 && !i.effects[PBEffects::SkipTurn]
        side=(pbIsOpposing?(i.index)) ? 1 : 0
        owner=pbGetOwnerIndex(i.index)
        if @megaEvolution[side][owner]==i.index
          pbMegaEvolve(i.index)
          megaevolved.push(i.index)
        end
      end
    end
    if megaevolved.length>0
      for i in priority
        i.pbAbilitiesOnSwitchIn(true) if megaevolved.include?(i.index)
      end
    end
    # Call at Pokémon
    for i in priority
      if @choices[i.index][0]==4 && !i.effects[PBEffects::SkipTurn]
        pbCall(i.index)
      end
    end
    # Switch out Pokémon
    @switching=true
    switched=[]
    for i in priority
      if @choices[i.index][0]==2 && !i.effects[PBEffects::SkipTurn]
        index=@choices[i.index][1] # party position of Pokémon to switch to
        newpokename=index
        if isConst?(pbParty(i.index)[index].ability,PBAbilities,:ILLUSION)
          newpokename=pbGetLastPokeInTeam(i.index)
        end
        self.lastMoveUser=i.index
        if !pbOwnedByPlayer?(i.index)
          owner=pbGetOwner(i.index)
          pbDisplayBrief(_INTL("{1} withdrew {2}!",owner.fullname,i.name))
          PBDebug.log("[Withdrew Pokémon] Opponent withdrew #{i.pbThis(true)}")
        else
          pbDisplayBrief(_INTL("{1}, that's enough!\r\nCome back!",i.name))
          PBDebug.log("[Withdrew Pokémon] Player withdrew #{i.pbThis(true)}")
        end
        for j in priority
          next if !i.pbIsOpposing?(j.index)
          # if Pursuit and this target ("i") was chosen
          if pbChoseMoveFunctionCode?(j.index,0x88) && # Pursuit
             !j.hasMovedThisRound?
            if j.status!=PBStatuses::SLEEP && j.status!=PBStatuses::FROZEN &&
               !j.effects[PBEffects::SkyDrop] &&
               (!j.hasWorkingAbility(:TRUANT) || !j.effects[PBEffects::Truant])
              @choices[j.index][3]=i.index # Make sure to target the switching Pokémon
              j.pbUseMove(@choices[j.index]) # This calls pbGainEXP as appropriate
              j.effects[PBEffects::Pursuit]=true
              @switching=false
              return if @decision>0
            end
          end
          break if i.fainted?
        end
        if !pbRecallAndReplace(i.index,index,newpokename)
          # If a forced switch somehow occurs here in single battles
          # the attack phase now ends
          if !@doublebattle
            @switching=false
            return
          end
        else
          switched.push(i.index)
        end
      end
    end
    if switched.length>0
      for i in priority
        i.pbAbilitiesOnSwitchIn(true) if switched.include?(i.index)
      end
    end
    @switching=false
    # Use items
    for i in priority
      if @choices[i.index][0]==3 && !i.effects[PBEffects::SkipTurn]
        if pbIsOpposing?(i.index)
          # Opponent use item
          pbEnemyUseItem(@choices[i.index][1],i)
        else
          # Player use item
          item=@choices[i.index][1]
          if item>0
            usetype=$ItemData[item][ITEMBATTLEUSE]
            if usetype==1 || usetype==3
              if @choices[i.index][2]>=0
                pbUseItemOnPokemon(item,@choices[i.index][2],i,@scene)
              end
            elsif usetype==2 || usetype==4
              if !ItemHandlers.hasUseInBattle(item) # Poké Ball/Poké Doll used already
                pbUseItemOnBattler(item,@choices[i.index][2],i,@scene)
              end
            end
          end
        end
      end
    end
    # Use attacks
    for i in priority
      next if i.effects[PBEffects::SkipTurn]
      if pbChoseMoveFunctionCode?(i.index,0x115) # Focus Punch
        pbCommonAnimation("FocusPunch",i,nil)
        pbDisplay(_INTL("{1} is tightening its focus!",i.pbThis))
      end
    end
    10.times do
      # Forced to go next
      advance=false
      for i in priority
        next if !i.effects[PBEffects::MoveNext]
        next if i.hasMovedThisRound? || i.effects[PBEffects::SkipTurn]
        advance=i.pbProcessTurn(@choices[i.index])
        break if advance
      end
      return if @decision>0
      next if advance
      # Regular priority order
      for i in priority
        next if i.effects[PBEffects::Quash]
        next if i.hasMovedThisRound? || i.effects[PBEffects::SkipTurn]
        advance=i.pbProcessTurn(@choices[i.index])
        break if advance
      end
      return if @decision>0
      next if advance
      # Quashed
      for i in priority
        next if !i.effects[PBEffects::Quash]
        next if i.hasMovedThisRound? || i.effects[PBEffects::SkipTurn]
        advance=i.pbProcessTurn(@choices[i.index])
        break if advance
      end
      return if @decision>0
      next if advance
      # Check for all done
      for i in priority
        advance=true if @choices[i.index][0]==1 && !i.hasMovedThisRound? &&
                        !i.effects[PBEffects::SkipTurn]
        break if advance
      end
      next if advance
      break
    end
    10.times do
      @scene.pbGraphicsUpdate
      @scene.pbInputUpdate
      @scene.pbFrameUpdate
    end
  end

################################################################################
# End of round.
################################################################################
  def pbEndOfRoundPhase
    PBDebug.log("[End of round]")
    for i in 0...4
      @battlers[i].effects[PBEffects::Electrify]=false
      @battlers[i].effects[PBEffects::Endure]=false
      @battlers[i].effects[PBEffects::FirstPledge]=0
      @battlers[i].effects[PBEffects::HyperBeam]-=1 if @battlers[i].effects[PBEffects::HyperBeam]>0
      @battlers[i].effects[PBEffects::KingsShield]=false
      @battlers[i].effects[PBEffects::LifeOrb]=false
      @battlers[i].effects[PBEffects::MoveNext]=false
      @battlers[i].effects[PBEffects::Powder]=false
      @battlers[i].effects[PBEffects::Protect]=false
      @battlers[i].effects[PBEffects::ProtectNegation]=false
      @battlers[i].effects[PBEffects::Quash]=false
      @battlers[i].effects[PBEffects::Roost]=false
      @battlers[i].effects[PBEffects::SpikyShield]=false
    end
    @usepriority=false  # recalculate priority
    priority=pbPriority(true) # Ignoring Quick Claw here
    # Weather
    case @weather
    when PBWeather::SUNNYDAY
      @weatherduration=@weatherduration-1 if @weatherduration>0
      if @weatherduration==0
        pbDisplay(_INTL("The sunlight faded."))
        @weather=0
        PBDebug.log("[End of effect] Sunlight weather ended")
      else
        pbCommonAnimation("Sunny",nil,nil)
#        pbDisplay(_INTL("The sunlight is strong."))
        if pbWeather==PBWeather::SUNNYDAY
          for i in priority
            if i.hasWorkingAbility(:SOLARPOWER)
              PBDebug.log("[Ability triggered] #{i.pbThis}'s Solar Power")
              @scene.pbDamageAnimation(i,0)
              i.pbReduceHP((i.totalhp/8).floor)
              pbDisplay(_INTL("{1} was hurt by the sunlight!",i.pbThis))
              if i.fainted?
                return if !i.pbFaint
              end
            end
          end
        end
      end
    when PBWeather::RAINDANCE
      @weatherduration=@weatherduration-1 if @weatherduration>0
      if @weatherduration==0
        pbDisplay(_INTL("The rain stopped."))
        @weather=0
        PBDebug.log("[End of effect] Rain weather ended")
      else
        pbCommonAnimation("Rain",nil,nil)
#        pbDisplay(_INTL("Rain continues to fall."))
      end
    when PBWeather::SANDSTORM
      @weatherduration=@weatherduration-1 if @weatherduration>0
      if @weatherduration==0
        pbDisplay(_INTL("The sandstorm subsided."))
        @weather=0
        PBDebug.log("[End of effect] Sandstorm weather ended")
      else
        pbCommonAnimation("Sandstorm",nil,nil)
#        pbDisplay(_INTL("The sandstorm rages."))
        if pbWeather==PBWeather::SANDSTORM
          PBDebug.log("[Lingering effect triggered] Sandstorm weather damage")
          for i in priority
            next if i.fainted?
            if !i.pbHasType?(:GROUND) && !i.pbHasType?(:ROCK) && !i.pbHasType?(:STEEL) &&
               !i.hasWorkingAbility(:SANDVEIL) &&
               !i.hasWorkingAbility(:SANDRUSH) &&
               !i.hasWorkingAbility(:SANDFORCE) &&
               !i.hasWorkingAbility(:MAGICGUARD) &&
               !i.hasWorkingAbility(:OVERCOAT) &&
               !i.hasWorkingItem(:SAFETYGOGGLES) &&
               ![0xCA,0xCB].include?(PBMoveData.new(i.effects[PBEffects::TwoTurnAttack]).function) # Dig, Dive
              @scene.pbDamageAnimation(i,0)
              i.pbReduceHP((i.totalhp/16).floor)
              pbDisplay(_INTL("{1} is buffeted by the sandstorm!",i.pbThis))
              if i.fainted?
                return if !i.pbFaint
              end
            end
          end
        end
      end
    when PBWeather::HAIL
      @weatherduration=@weatherduration-1 if @weatherduration>0
      if @weatherduration==0
        pbDisplay(_INTL("The hail stopped."))
        @weather=0
        PBDebug.log("[End of effect] Hail weather ended")
      else
        pbCommonAnimation("Hail",nil,nil)
#        pbDisplay(_INTL("Hail continues to fall."))
        if pbWeather==PBWeather::HAIL
          PBDebug.log("[Lingering effect triggered] Hail weather damage")
          for i in priority
            next if i.fainted?
            if !i.pbHasType?(:ICE) &&
               !i.hasWorkingAbility(:ICEBODY) &&
               !i.hasWorkingAbility(:SNOWCLOAK) &&
               !i.hasWorkingAbility(:MAGICGUARD) &&
               !i.hasWorkingAbility(:OVERCOAT) &&
               !i.hasWorkingItem(:SAFETYGOGGLES) &&
               ![0xCA,0xCB].include?(PBMoveData.new(i.effects[PBEffects::TwoTurnAttack]).function) # Dig, Dive
              @scene.pbDamageAnimation(i,0)
              i.pbReduceHP((i.totalhp/16).floor)
              pbDisplay(_INTL("{1} is buffeted by the hail!",i.pbThis))
              if i.fainted?
                return if !i.pbFaint
              end
            end
          end
        end
      end
    when PBWeather::HEAVYRAIN
      hasabil=false
      for i in 0...4
        if isConst?(@battlers[i].ability,PBAbilities,:PRIMORDIALSEA) && !@battlers[i].fainted?
          hasabil=true; break
        end
      end
      @weatherduration=0 if !hasabil
      if @weatherduration==0
        pbDisplay(_INTL("The heavy rain stopped."))
        @weather=0
        PBDebug.log("[End of effect] Primordial Sea's rain weather ended")
      else
        pbCommonAnimation("HeavyRain",nil,nil)
#        pbDisplay(_INTL("It is raining heavily."))
      end
    when PBWeather::HARSHSUN
      hasabil=false
      for i in 0...4
        if isConst?(@battlers[i].ability,PBAbilities,:DESOLATELAND) && !@battlers[i].fainted?
          hasabil=true; break
        end
      end
      @weatherduration=0 if !hasabil
      if @weatherduration==0
        pbDisplay(_INTL("The harsh sunlight faded."))
        @weather=0
        PBDebug.log("[End of effect] Desolate Land's sunlight weather ended")
      else
        pbCommonAnimation("HarshSun",nil,nil)
#        pbDisplay(_INTL("The sunlight is extremely harsh."))
        if pbWeather==PBWeather::HARSHSUN
          for i in priority
            if i.hasWorkingAbility(:SOLARPOWER)
              PBDebug.log("[Ability triggered] #{i.pbThis}'s Solar Power")
              @scene.pbDamageAnimation(i,0)
              i.pbReduceHP((i.totalhp/8).floor)
              pbDisplay(_INTL("{1} was hurt by the sunlight!",i.pbThis))
              if i.fainted?
                return if !i.pbFaint
              end
            end
          end
        end
      end
    when PBWeather::STRONGWINDS
      hasabil=false
      for i in 0...4
        if isConst?(@battlers[i].ability,PBAbilities,:DELTASTREAM) && !@battlers[i].fainted?
          hasabil=true; break
        end
      end
      @weatherduration=0 if !hasabil
      if @weatherduration==0
        pbDisplay(_INTL("The air current subsided."))
        @weather=0
        PBDebug.log("[End of effect] Delta Stream's wind weather ended")
      else
        pbCommonAnimation("StrongWinds",nil,nil)
#        pbDisplay(_INTL("The wind is strong."))
      end
    end
    # Shadow Sky weather
    if isConst?(@weather,PBWeather,:SHADOWSKY)
      @weatherduration=@weatherduration-1 if @weatherduration>0
      if @weatherduration==0
        pbDisplay(_INTL("The shadow sky faded."))
        @weather=0
        PBDebug.log("[End of effect] Shadow Sky weather ended")
      else
        pbCommonAnimation("ShadowSky",nil,nil)
#        pbDisplay(_INTL("The shadow sky continues."));
        if isConst?(pbWeather,PBWeather,:SHADOWSKY)
          PBDebug.log("[Lingering effect triggered] Shadow Sky weather damage")
          for i in priority
            next if i.fainted?
            if !i.isShadow?
              @scene.pbDamageAnimation(i,0)
              i.pbReduceHP((i.totalhp/16).floor)
              pbDisplay(_INTL("{1} was hurt by the shadow sky!",i.pbThis))
              if i.fainted?
                return if !i.pbFaint
              end
            end
          end
        end
      end
    end
    # Future Sight/Doom Desire
    for i in battlers   # not priority
      next if i.fainted?
      if i.effects[PBEffects::FutureSight]>0
        i.effects[PBEffects::FutureSight]-=1
        if i.effects[PBEffects::FutureSight]==0
          move=i.effects[PBEffects::FutureSightMove]
          PBDebug.log("[Lingering effect triggered] #{PBMoves.getName(move)} struck #{i.pbThis(true)}")
          pbDisplay(_INTL("{1} took the {2} attack!",i.pbThis,PBMoves.getName(move)))
          moveuser=nil
          for j in battlers
            next if j.pbIsOpposing?(i.effects[PBEffects::FutureSightUserPos])
            if j.pokemonIndex==i.effects[PBEffects::FutureSightUser] && !j.fainted?
              moveuser=j; break
            end
          end
          if !moveuser
            party=pbParty(i.effects[PBEffects::FutureSightUserPos])
            if party[i.effects[PBEffects::FutureSightUser]].hp>0
              moveuser=PokeBattle_Battler.new(self,i.effects[PBEffects::FutureSightUserPos])
              moveuser.pbInitDummyPokemon(party[i.effects[PBEffects::FutureSightUser]],
                                          i.effects[PBEffects::FutureSightUser])
            end
          end
          if !moveuser
            pbDisplay(_INTL("But it failed!"))
          else
            @futuresight=true
            moveuser.pbUseMoveSimple(move,-1,i.index)
            @futuresight=false
          end
          i.effects[PBEffects::FutureSight]=0
          i.effects[PBEffects::FutureSightMove]=0
          i.effects[PBEffects::FutureSightUser]=-1
          i.effects[PBEffects::FutureSightUserPos]=-1
          if i.fainted?
            return if !i.pbFaint
            next
          end
        end
      end
    end
    for i in priority
      next if i.fainted?
      # Rain Dish
      if i.hasWorkingAbility(:RAINDISH) && i.effects[PBEffects::HealBlock]==0 &&
         (pbWeather==PBWeather::RAINDANCE ||
         pbWeather==PBWeather::HEAVYRAIN)
        PBDebug.log("[Ability triggered] #{i.pbThis}'s Rain Dish")
        hpgain=i.pbRecoverHP((i.totalhp/16).floor,true)
        pbDisplay(_INTL("{1}'s {2} restored its HP a little!",i.pbThis,PBAbilities.getName(i.ability))) if hpgain>0
      end
      # Dry Skin
      if i.hasWorkingAbility(:DRYSKIN)
        if (pbWeather==PBWeather::RAINDANCE || pbWeather==PBWeather::HEAVYRAIN) &&
           i.effects[PBEffects::HealBlock]==0
          PBDebug.log("[Ability triggered] #{i.pbThis}'s Dry Skin (in rain)")
          hpgain=i.pbRecoverHP((i.totalhp/8).floor,true)
          pbDisplay(_INTL("{1}'s {2} was healed by the rain!",i.pbThis,PBAbilities.getName(i.ability))) if hpgain>0
        elsif pbWeather==PBWeather::SUNNYDAY ||
              pbWeather==PBWeather::HARSHSUN
          PBDebug.log("[Ability triggered] #{i.pbThis}'s Dry Skin (in sun)")
          @scene.pbDamageAnimation(i,0)
          hploss=i.pbReduceHP((i.totalhp/8).floor)
          pbDisplay(_INTL("{1}'s {2} was hurt by the sunlight!",i.pbThis,PBAbilities.getName(i.ability))) if hploss>0
        end
      end
      # Ice Body
      if i.hasWorkingAbility(:ICEBODY) && pbWeather==PBWeather::HAIL &&
         i.effects[PBEffects::HealBlock]==0
        PBDebug.log("[Ability triggered] #{i.pbThis}'s Ice Body")
        hpgain=i.pbRecoverHP((i.totalhp/16).floor,true)
        pbDisplay(_INTL("{1}'s {2} restored its HP a little!",i.pbThis,PBAbilities.getName(i.ability))) if hpgain>0
      end
      if i.fainted?
        return if !i.pbFaint
      end
    end
    # Wish
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Wish]>0
        i.effects[PBEffects::Wish]-=1
        if i.effects[PBEffects::Wish]==0
          PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Wish")
          hpgain=i.pbRecoverHP(i.effects[PBEffects::WishAmount],true)
          if hpgain>0
            wishmaker=pbThisEx(i.index,i.effects[PBEffects::WishMaker])
            pbDisplay(_INTL("{1}'s wish came true!",wishmaker))
          end
        end
      end
    end
    # Fire Pledge + Grass Pledge combination damage
    for i in 0...2
      if sides[i].effects[PBEffects::SeaOfFire]>0 &&
         pbWeather!=PBWeather::RAINDANCE &&
         pbWeather!=PBWeather::HEAVYRAIN
        @battle.pbCommonAnimation("SeaOfFire",nil,nil) if i==0
        @battle.pbCommonAnimation("SeaOfFireOpp",nil,nil) if i==1
        for j in priority
          next if (j.index&1)!=i
          next if j.pbHasType?(:FIRE) || j.hasWorkingAbility(:MAGICGUARD)
          @scene.pbDamageAnimation(j,0)
          hploss=j.pbReduceHP((j.totalhp/8).floor)
          pbDisplay(_INTL("{1} is hurt by the sea of fire!",j.pbThis)) if hploss>0
          if j.fainted?
            return if !j.pbFaint
          end
        end
      end
    end
    for i in priority
      next if i.fainted?
      # Shed Skin, Hydration
      if (i.hasWorkingAbility(:SHEDSKIN) && pbRandom(10)<3) ||
         (i.hasWorkingAbility(:HYDRATION) && (pbWeather==PBWeather::RAINDANCE ||
                                              pbWeather==PBWeather::HEAVYRAIN))
        if i.status>0
          PBDebug.log("[Ability triggered] #{i.pbThis}'s #{PBAbilities.getName(i.ability)}")
          s=i.status
          i.pbCureStatus(false)
          case s
          when PBStatuses::SLEEP
            pbDisplay(_INTL("{1}'s {2} cured its sleep problem!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::POISON
            pbDisplay(_INTL("{1}'s {2} cured its poison problem!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::BURN
            pbDisplay(_INTL("{1}'s {2} healed its burn!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::PARALYSIS
            pbDisplay(_INTL("{1}'s {2} cured its paralysis!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::FROZEN
            pbDisplay(_INTL("{1}'s {2} thawed it out!",i.pbThis,PBAbilities.getName(i.ability)))
          end
        end
      end
      # Healer
      if i.hasWorkingAbility(:HEALER) && pbRandom(10)<3
        partner=i.pbPartner
        if partner && partner.status>0
          PBDebug.log("[Ability triggered] #{i.pbThis}'s #{PBAbilities.getName(i.ability)}")
          s=partner.status
          partner.pbCureStatus(false)
          case s
          when PBStatuses::SLEEP
            pbDisplay(_INTL("{1}'s {2} cured its partner's sleep problem!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::POISON
            pbDisplay(_INTL("{1}'s {2} cured its partner's poison problem!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::BURN
            pbDisplay(_INTL("{1}'s {2} healed its partner's burn!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::PARALYSIS
            pbDisplay(_INTL("{1}'s {2} cured its partner's paralysis!",i.pbThis,PBAbilities.getName(i.ability)))
          when PBStatuses::FROZEN
            pbDisplay(_INTL("{1}'s {2} thawed its partner out!",i.pbThis,PBAbilities.getName(i.ability)))
          end
        end
      end
    end
    for i in priority
      next if i.fainted?
      # Grassy Terrain (healing)
      if @field.effects[PBEffects::GrassyTerrain]>0 && !i.isAirborne?
        if i.effects[PBEffects::HealBlock]==0
          hpgain=i.pbRecoverHP((i.totalhp/16).floor,true)
          pbDisplay(_INTL("{1}'s HP was restored.",i.pbThis)) if hpgain>0
        end
      end
      # Held berries/Leftovers/Black Sludge
      i.pbBerryCureCheck(true)
      if i.fainted?
        return if !i.pbFaint
      end
    end
    # Aqua Ring
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::AquaRing]
        PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Aqua Ring")
        hpgain=(i.totalhp/16).floor
        hpgain=(hpgain*1.3).floor if i.hasWorkingItem(:BIGROOT)
        hpgain=i.pbRecoverHP(hpgain,true)
        pbDisplay(_INTL("Aqua Ring restored {1}'s HP!",i.pbThis)) if hpgain>0
      end
    end
    # Ingrain
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Ingrain]
        PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Ingrain")
        hpgain=(i.totalhp/16).floor
        hpgain=(hpgain*1.3).floor if i.hasWorkingItem(:BIGROOT)
        hpgain=i.pbRecoverHP(hpgain,true)
        pbDisplay(_INTL("{1} absorbed nutrients with its roots!",i.pbThis)) if hpgain>0
      end
    end
    # Leech Seed
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::LeechSeed]>=0 && !i.hasWorkingAbility(:MAGICGUARD)
        recipient=@battlers[i.effects[PBEffects::LeechSeed]]
        if recipient && !recipient.fainted?
          PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Leech Seed")
          pbCommonAnimation("LeechSeed",recipient,i)
          hploss=i.pbReduceHP((i.totalhp/8).floor,true)
          if i.hasWorkingAbility(:LIQUIDOOZE)
            recipient.pbReduceHP(hploss,true)
            pbDisplay(_INTL("{1} sucked up the liquid ooze!",recipient.pbThis))
          else
            if recipient.effects[PBEffects::HealBlock]==0
              hploss=(hploss*1.3).floor if recipient.hasWorkingItem(:BIGROOT)
              recipient.pbRecoverHP(hploss,true)
            end
            pbDisplay(_INTL("{1}'s health was sapped by Leech Seed!",i.pbThis))
          end
          if i.fainted?
            return if !i.pbFaint
          end
          if recipient.fainted?
            return if !recipient.pbFaint
          end
        end
      end
    end
    for i in priority
      next if i.fainted?
      # Poison/Bad poison
      if i.status==PBStatuses::POISON
        if i.statusCount>0
          i.effects[PBEffects::Toxic]+=1
          i.effects[PBEffects::Toxic]=[15,i.effects[PBEffects::Toxic]].min
        end
        if i.hasWorkingAbility(:POISONHEAL)
          pbCommonAnimation("Poison",i,nil)
          if i.effects[PBEffects::HealBlock]==0 && i.hp<i.totalhp
            PBDebug.log("[Ability triggered] #{i.pbThis}'s Poison Heal")
            i.pbRecoverHP((i.totalhp/8).floor,true)
            pbDisplay(_INTL("{1} is healed by poison!",i.pbThis))
          end
        else
          if !i.hasWorkingAbility(:MAGICGUARD)
            PBDebug.log("[Status damage] #{i.pbThis} took damage from poison/toxic")
            if i.statusCount==0
              i.pbReduceHP((i.totalhp/8).floor)
            else
              i.pbReduceHP(((i.totalhp*i.effects[PBEffects::Toxic])/16).floor)
            end
            i.pbContinueStatus
          end
        end
      end
      # Burn
      if i.status==PBStatuses::BURN
        if !i.hasWorkingAbility(:MAGICGUARD)
          PBDebug.log("[Status damage] #{i.pbThis} took damage from burn")
          if i.hasWorkingAbility(:HEATPROOF)
            PBDebug.log("[Ability triggered] #{i.pbThis}'s Heatproof")
            i.pbReduceHP((i.totalhp/16).floor)
          else
            i.pbReduceHP((i.totalhp/8).floor)
          end
        end
        i.pbContinueStatus
      end
      # Nightmare
      if i.effects[PBEffects::Nightmare]
        if i.status==PBStatuses::SLEEP
          if !i.hasWorkingAbility(:MAGICGUARD)
            PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s nightmare")
            i.pbReduceHP((i.totalhp/4).floor,true)
            pbDisplay(_INTL("{1} is locked in a nightmare!",i.pbThis))
          end
        else
          i.effects[PBEffects::Nightmare]=false
        end
      end
      if i.fainted?
        return if !i.pbFaint
        next
      end
    end
    # Curse
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Curse] && !i.hasWorkingAbility(:MAGICGUARD)
        PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s curse")
        i.pbReduceHP((i.totalhp/4).floor,true)
        pbDisplay(_INTL("{1} is afflicted by the curse!",i.pbThis))
      end
      if i.fainted?
        return if !i.pbFaint
        next
      end
    end
    # Multi-turn attacks (Bind/Clamp/Fire Spin/Magma Storm/Sand Tomb/Whirlpool/Wrap)
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::MultiTurn]>0
        i.effects[PBEffects::MultiTurn]-=1
        movename=PBMoves.getName(i.effects[PBEffects::MultiTurnAttack])
        if i.effects[PBEffects::MultiTurn]==0
          PBDebug.log("[End of effect] Trapping move #{movename} affecting #{i.pbThis} ended")
          pbDisplay(_INTL("{1} was freed from {2}!",i.pbThis,movename))
        else
          if isConst?(i.effects[PBEffects::MultiTurnAttack],PBMoves,:BIND)
            pbCommonAnimation("Bind",i,nil)
          elsif isConst?(i.effects[PBEffects::MultiTurnAttack],PBMoves,:CLAMP)
            pbCommonAnimation("Clamp",i,nil)
          elsif isConst?(i.effects[PBEffects::MultiTurnAttack],PBMoves,:FIRESPIN)
            pbCommonAnimation("FireSpin",i,nil)
          elsif isConst?(i.effects[PBEffects::MultiTurnAttack],PBMoves,:MAGMASTORM)
            pbCommonAnimation("MagmaStorm",i,nil)
          elsif isConst?(i.effects[PBEffects::MultiTurnAttack],PBMoves,:SANDTOMB)
            pbCommonAnimation("SandTomb",i,nil)
          elsif isConst?(i.effects[PBEffects::MultiTurnAttack],PBMoves,:WRAP)
            pbCommonAnimation("Wrap",i,nil)
          elsif isConst?(i.effects[PBEffects::MultiTurnAttack],PBMoves,:INFESTATION)
            pbCommonAnimation("Infestation",i,nil)
          else
            pbCommonAnimation("Wrap",i,nil)
          end
          if !i.hasWorkingAbility(:MAGICGUARD)
            PBDebug.log("[Lingering effect triggered] #{i.pbThis} took damage from trapping move #{movename}")
            @scene.pbDamageAnimation(i,0)
            amt=(USENEWBATTLEMECHANICS) ? (i.totalhp/8).floor : (i.totalhp/16).floor
            if @battlers[i.effects[PBEffects::MultiTurnUser]].hasWorkingItem(:BINDINGBAND)
              amt=(USENEWBATTLEMECHANICS) ? (i.totalhp/6).floor : (i.totalhp/8).floor
            end
            i.pbReduceHP(amt)
            pbDisplay(_INTL("{1} is hurt by {2}!",i.pbThis,movename))
          end
        end
      end  
      if i.fainted?
        return if !i.pbFaint
      end
    end
    # Taunt
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Taunt]>0
        i.effects[PBEffects::Taunt]-=1
        if i.effects[PBEffects::Taunt]==0
          pbDisplay(_INTL("{1}'s taunt wore off!",i.pbThis))
          PBDebug.log("[End of effect] #{i.pbThis} is no longer taunted")
        end 
      end
    end
    # Encore
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Encore]>0
        if i.moves[i.effects[PBEffects::EncoreIndex]].id!=i.effects[PBEffects::EncoreMove]
          i.effects[PBEffects::Encore]=0
          i.effects[PBEffects::EncoreIndex]=0
          i.effects[PBEffects::EncoreMove]=0
          PBDebug.log("[End of effect] #{i.pbThis} is no longer encored (encored move was lost)")
        else
          i.effects[PBEffects::Encore]-=1
          if i.effects[PBEffects::Encore]==0 || i.moves[i.effects[PBEffects::EncoreIndex]].pp==0
            i.effects[PBEffects::Encore]=0
            pbDisplay(_INTL("{1}'s encore ended!",i.pbThis))
            PBDebug.log("[End of effect] #{i.pbThis} is no longer encored")
          end 
        end
      end
    end
    # Disable/Cursed Body
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Disable]>0
        i.effects[PBEffects::Disable]-=1
        if i.effects[PBEffects::Disable]==0
          i.effects[PBEffects::DisableMove]=0
          pbDisplay(_INTL("{1} is no longer disabled!",i.pbThis))
          PBDebug.log("[End of effect] #{i.pbThis} is no longer disabled")
        end
      end
    end
    # Magnet Rise
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::MagnetRise]>0
        i.effects[PBEffects::MagnetRise]-=1
        if i.effects[PBEffects::MagnetRise]==0
          pbDisplay(_INTL("{1} stopped levitating.",i.pbThis))
          PBDebug.log("[End of effect] #{i.pbThis} is no longer levitating by Magnet Rise")
        end
      end
    end
    # Telekinesis
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Telekinesis]>0
        i.effects[PBEffects::Telekinesis]-=1
        if i.effects[PBEffects::Telekinesis]==0
          pbDisplay(_INTL("{1} stopped levitating.",i.pbThis))
          PBDebug.log("[End of effect] #{i.pbThis} is no longer levitating by Telekinesis")
        end
      end
    end
    # Heal Block
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::HealBlock]>0
        i.effects[PBEffects::HealBlock]-=1
        if i.effects[PBEffects::HealBlock]==0
          pbDisplay(_INTL("{1}'s Heal Block wore off!",i.pbThis))
          PBDebug.log("[End of effect] #{i.pbThis} is no longer Heal Blocked")
        end
      end
    end
    # Embargo
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Embargo]>0
        i.effects[PBEffects::Embargo]-=1
        if i.effects[PBEffects::Embargo]==0
          pbDisplay(_INTL("{1} can use items again!",i.pbThis(true)))
          PBDebug.log("[End of effect] #{i.pbThis} is no longer affected by an embargo")
        end
      end
    end
    # Yawn
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Yawn]>0
        i.effects[PBEffects::Yawn]-=1
        if i.effects[PBEffects::Yawn]==0 && i.pbCanSleepYawn?
          PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Yawn")
          i.pbSleep
          i.pbBerryCureCheck
        end
      end
    end
    # Perish Song
    perishSongUsers=[]
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::PerishSong]>0
        i.effects[PBEffects::PerishSong]-=1
        pbDisplay(_INTL("{1}'s perish count fell to {2}!",i.pbThis,i.effects[PBEffects::PerishSong]))
        PBDebug.log("[Lingering effect triggered] #{i.pbThis}'s Perish Song count dropped to #{i.effects[PBEffects::PerishSong]}")
        if i.effects[PBEffects::PerishSong]==0
          perishSongUsers.push(i.effects[PBEffects::PerishSongUser])
          i.pbReduceHP(i.hp,true)
        end
      end
      if i.fainted?
        return if !i.pbFaint
      end
    end
    if perishSongUsers.length>0
      # If all remaining Pokemon fainted by a Perish Song triggered by a single side
      if (perishSongUsers.find_all{|item| pbIsOpposing?(item) }.length==perishSongUsers.length) ||
         (perishSongUsers.find_all{|item| !pbIsOpposing?(item) }.length==perishSongUsers.length)
        pbJudgeCheckpoint(@battlers[perishSongUsers[0]])
      end
    end
    if @decision>0
      pbGainEXP
      return
    end
    # Reflect
    for i in 0...2
      if sides[i].effects[PBEffects::Reflect]>0
        sides[i].effects[PBEffects::Reflect]-=1
        if sides[i].effects[PBEffects::Reflect]==0
          pbDisplay(_INTL("Your team's Reflect faded!")) if i==0
          pbDisplay(_INTL("The opposing team's Reflect faded!")) if i==1
          PBDebug.log("[End of effect] Reflect ended on the player's side") if i==0
          PBDebug.log("[End of effect] Reflect ended on the opponent's side") if i==1
        end
      end
    end
    # Light Screen
    for i in 0...2
      if sides[i].effects[PBEffects::LightScreen]>0
        sides[i].effects[PBEffects::LightScreen]-=1
        if sides[i].effects[PBEffects::LightScreen]==0
          pbDisplay(_INTL("Your team's Light Screen faded!")) if i==0
          pbDisplay(_INTL("The opposing team's Light Screen faded!")) if i==1
          PBDebug.log("[End of effect] Light Screen ended on the player's side") if i==0
          PBDebug.log("[End of effect] Light Screen ended on the opponent's side") if i==1
        end
      end
    end
    # Safeguard
    for i in 0...2
      if sides[i].effects[PBEffects::Safeguard]>0
        sides[i].effects[PBEffects::Safeguard]-=1
        if sides[i].effects[PBEffects::Safeguard]==0
          pbDisplay(_INTL("Your team is no longer protected by Safeguard!")) if i==0
          pbDisplay(_INTL("The opposing team is no longer protected by Safeguard!")) if i==1
          PBDebug.log("[End of effect] Safeguard ended on the player's side") if i==0
          PBDebug.log("[End of effect] Safeguard ended on the opponent's side") if i==1
        end
      end
    end
    # Mist
    for i in 0...2
      if sides[i].effects[PBEffects::Mist]>0
        sides[i].effects[PBEffects::Mist]-=1
        if sides[i].effects[PBEffects::Mist]==0
          pbDisplay(_INTL("Your team's Mist faded!")) if i==0
          pbDisplay(_INTL("The opposing team's Mist faded!")) if i==1
          PBDebug.log("[End of effect] Mist ended on the player's side") if i==0
          PBDebug.log("[End of effect] Mist ended on the opponent's side") if i==1
        end
      end
    end
    # Tailwind
    for i in 0...2
      if sides[i].effects[PBEffects::Tailwind]>0
        sides[i].effects[PBEffects::Tailwind]-=1
        if sides[i].effects[PBEffects::Tailwind]==0
          pbDisplay(_INTL("Your team's Tailwind petered out!")) if i==0
          pbDisplay(_INTL("The opposing team's Tailwind petered out!")) if i==1
          PBDebug.log("[End of effect] Tailwind ended on the player's side") if i==0
          PBDebug.log("[End of effect] Tailwind ended on the opponent's side") if i==1
        end
      end
    end
    # Lucky Chant
    for i in 0...2
      if sides[i].effects[PBEffects::LuckyChant]>0
        sides[i].effects[PBEffects::LuckyChant]-=1
        if sides[i].effects[PBEffects::LuckyChant]==0
          pbDisplay(_INTL("Your team's Lucky Chant faded!")) if i==0
          pbDisplay(_INTL("The opposing team's Lucky Chant faded!")) if i==1
          PBDebug.log("[End of effect] Lucky Chant ended on the player's side") if i==0
          PBDebug.log("[End of effect] Lucky Chant ended on the opponent's side") if i==1
        end
      end
    end
    # End of Pledge move combinations
    for i in 0...2
      if sides[i].effects[PBEffects::Swamp]>0
        sides[i].effects[PBEffects::Swamp]-=1
        if sides[i].effects[PBEffects::Swamp]==0
          pbDisplay(_INTL("The swamp around your team disappeared!")) if i==0
          pbDisplay(_INTL("The swamp around the opposing team disappeared!")) if i==1
          PBDebug.log("[End of effect] Grass Pledge's swamp ended on the player's side") if i==0
          PBDebug.log("[End of effect] Grass Pledge's swamp ended on the opponent's side") if i==1
        end
      end
      if sides[i].effects[PBEffects::SeaOfFire]>0
        sides[i].effects[PBEffects::SeaOfFire]-=1
        if sides[i].effects[PBEffects::SeaOfFire]==0
          pbDisplay(_INTL("The sea of fire around your team disappeared!")) if i==0
          pbDisplay(_INTL("The sea of fire around the opposing team disappeared!")) if i==1
          PBDebug.log("[End of effect] Fire Pledge's sea of fire ended on the player's side") if i==0
          PBDebug.log("[End of effect] Fire Pledge's sea of fire ended on the opponent's side") if i==1
        end
      end
      if sides[i].effects[PBEffects::Rainbow]>0
        sides[i].effects[PBEffects::Rainbow]-=1
        if sides[i].effects[PBEffects::Rainbow]==0
          pbDisplay(_INTL("The rainbow around your team disappeared!")) if i==0
          pbDisplay(_INTL("The rainbow around the opposing team disappeared!")) if i==1
          PBDebug.log("[End of effect] Water Pledge's rainbow ended on the player's side") if i==0
          PBDebug.log("[End of effect] Water Pledge's rainbow ended on the opponent's side") if i==1
        end
      end
    end
    # Gravity
    if @field.effects[PBEffects::Gravity]>0
      @field.effects[PBEffects::Gravity]-=1
      if @field.effects[PBEffects::Gravity]==0
        pbDisplay(_INTL("Gravity returned to normal."))
        PBDebug.log("[End of effect] Strong gravity ended")
      end
    end
    # Trick Room
    if @field.effects[PBEffects::TrickRoom]>0
      @field.effects[PBEffects::TrickRoom]-=1
      if @field.effects[PBEffects::TrickRoom]==0
        pbDisplay(_INTL("The twisted dimensions returned to normal."))
        PBDebug.log("[End of effect] Trick Room ended")
      end
    end
    # Wonder Room
    if @field.effects[PBEffects::WonderRoom]>0
      @field.effects[PBEffects::WonderRoom]-=1
      if @field.effects[PBEffects::WonderRoom]==0
        pbDisplay(_INTL("Wonder Room wore off, and the Defense and Sp. Def stats returned to normal!"))
        PBDebug.log("[End of effect] Wonder Room ended")
      end
    end
    # Magic Room
    if @field.effects[PBEffects::MagicRoom]>0
      @field.effects[PBEffects::MagicRoom]-=1
      if @field.effects[PBEffects::MagicRoom]==0
        pbDisplay(_INTL("The area returned to normal."))
        PBDebug.log("[End of effect] Magic Room ended")
      end
    end
    # Mud Sport
    if @field.effects[PBEffects::MudSportField]>0
      @field.effects[PBEffects::MudSportField]-=1
      if @field.effects[PBEffects::MudSportField]==0
        pbDisplay(_INTL("The effects of Mud Sport have faded."))
        PBDebug.log("[End of effect] Mud Sport ended")
      end
    end
    # Water Sport
    if @field.effects[PBEffects::WaterSportField]>0
      @field.effects[PBEffects::WaterSportField]-=1
      if @field.effects[PBEffects::WaterSportField]==0
        pbDisplay(_INTL("The effects of Water Sport have faded."))
        PBDebug.log("[End of effect] Water Sport ended")
      end
    end
    # Electric Terrain
    if @field.effects[PBEffects::ElectricTerrain]>0
      @field.effects[PBEffects::ElectricTerrain]-=1
      if @field.effects[PBEffects::ElectricTerrain]==0
        pbDisplay(_INTL("The electric current disappeared from the battlefield."))
        PBDebug.log("[End of effect] Electric Terrain ended")
      end
    end
    # Grassy Terrain (counting down)
    if @field.effects[PBEffects::GrassyTerrain]>0
      @field.effects[PBEffects::GrassyTerrain]-=1
      if @field.effects[PBEffects::GrassyTerrain]==0
        pbDisplay(_INTL("The grass disappeared from the battlefield."))
        PBDebug.log("[End of effect] Grassy Terrain ended")
      end
    end
    # Misty Terrain
    if @field.effects[PBEffects::MistyTerrain]>0
      @field.effects[PBEffects::MistyTerrain]-=1
      if @field.effects[PBEffects::MistyTerrain]==0
        pbDisplay(_INTL("The mist disappeared from the battlefield."))
        PBDebug.log("[End of effect] Misty Terrain ended")
      end
    end
    # Uproar
    for i in priority
      next if i.fainted?
      if i.effects[PBEffects::Uproar]>0
        for j in priority
          if !j.fainted? && j.status==PBStatuses::SLEEP && !j.hasWorkingAbility(:SOUNDPROOF)
            PBDebug.log("[Lingering effect triggered] Uproar woke up #{j.pbThis(true)}")
            j.pbCureStatus(false)
            pbDisplay(_INTL("{1} woke up in the uproar!",j.pbThis))
          end
        end
        i.effects[PBEffects::Uproar]-=1
        if i.effects[PBEffects::Uproar]==0
          pbDisplay(_INTL("{1} calmed down.",i.pbThis))
          PBDebug.log("[End of effect] #{i.pbThis} is no longer uproaring")
        else
          pbDisplay(_INTL("{1} is making an uproar!",i.pbThis)) 
        end
      end
    end
    for i in priority
      next if i.fainted?
      # Speed Boost
      # A Pokémon's turncount is 0 if it became active after the beginning of a round
      if i.turncount>0 && i.hasWorkingAbility(:SPEEDBOOST)
        if i.pbIncreaseStatWithCause(PBStats::SPEED,1,i,PBAbilities.getName(i.ability))
          PBDebug.log("[Ability triggered] #{i.pbThis}'s #{PBAbilities.getName(i.ability)}")
        end
      end
      # Bad Dreams
      if i.status==PBStatuses::SLEEP && !i.hasWorkingAbility(:MAGICGUARD)
        if i.pbOpposing1.hasWorkingAbility(:BADDREAMS) ||
           i.pbOpposing2.hasWorkingAbility(:BADDREAMS)
          PBDebug.log("[Ability triggered] #{i.pbThis}'s opponent's Bad Dreams")
          hploss=i.pbReduceHP((i.totalhp/8).floor,true)
          pbDisplay(_INTL("{1} is having a bad dream!",i.pbThis)) if hploss>0
        end
      end
      if i.fainted?
        return if !i.pbFaint
        next
      end
      # Pickup
      if i.hasWorkingAbility(:PICKUP) && i.item<=0
        item=0; index=-1; use=0
        for j in 0...4
          next if j==i.index
          if @battlers[j].effects[PBEffects::PickupUse]>use
            item=@battlers[j].effects[PBEffects::PickupItem]
            index=j
            use=@battlers[j].effects[PBEffects::PickupUse]
          end
        end
        if item>0
          i.item=item
          @battlers[index].effects[PBEffects::PickupItem]=0
          @battlers[index].effects[PBEffects::PickupUse]=0
          @battlers[index].pokemon.itemRecycle=0 if @battlers[index].pokemon.itemRecycle==item
          if !@opponent && # In a wild battle
             i.pokemon.itemInitial==0 &&
             @battlers[index].pokemon.itemInitial==item
            i.pokemon.itemInitial=item
            @battlers[index].pokemon.itemInitial=0
          end
          pbDisplay(_INTL("{1} found one {2}!",i.pbThis,PBItems.getName(item)))
          i.pbBerryCureCheck(true)
        end
      end
      # Harvest
      if i.hasWorkingAbility(:HARVEST) && i.item<=0 && i.pokemon.itemRecycle>0
        if pbIsBerry?(i.pokemon.itemRecycle) &&
           (pbWeather==PBWeather::SUNNYDAY || 
           pbWeather==PBWeather::HARSHSUN || pbRandom(10)<5)
          i.item=i.pokemon.itemRecycle
          i.pokemon.itemRecycle=0
          i.pokemon.itemInitial=i.item if i.pokemon.itemInitial==0
          pbDisplay(_INTL("{1} harvested one {2}!",i.pbThis,PBItems.getName(i.item)))
          i.pbBerryCureCheck(true)
        end
      end
      # Moody
      if i.hasWorkingAbility(:MOODY)
        randomup=[]; randomdown=[]
        for j in [PBStats::ATTACK,PBStats::DEFENSE,PBStats::SPEED,PBStats::SPATK,
                  PBStats::SPDEF,PBStats::ACCURACY,PBStats::EVASION]
          randomup.push(j) if i.pbCanIncreaseStatStage?(j,i)
          randomdown.push(j) if i.pbCanReduceStatStage?(j,i)
        end
        if randomup.length>0
          PBDebug.log("[Ability triggered] #{i.pbThis}'s Moody (raise stat)")
          r=pbRandom(randomup.length)
          i.pbIncreaseStatWithCause(randomup[r],2,i,PBAbilities.getName(i.ability))
          for j in 0...randomdown.length
            if randomdown[j]==randomup[r]
              randomdown[j]=nil; randomdown.compact!
              break
            end
          end
        end
        if randomdown.length>0
          PBDebug.log("[Ability triggered] #{i.pbThis}'s Moody (lower stat)")
          r=pbRandom(randomdown.length)
          i.pbReduceStatWithCause(randomdown[r],1,i,PBAbilities.getName(i.ability))
        end
      end
    end
    for i in priority
      next if i.fainted?
      # Toxic Orb
      if i.hasWorkingItem(:TOXICORB) && i.status==0 && i.pbCanPoison?(nil,false)
        PBDebug.log("[Item triggered] #{i.pbThis}'s Toxic Orb")
        i.pbPoison(nil,_INTL("{1} was badly poisoned by its {2}!",i.pbThis,
           PBItems.getName(i.item)),true)
      end
      # Flame Orb
      if i.hasWorkingItem(:FLAMEORB) && i.status==0 && i.pbCanBurn?(nil,false)
        PBDebug.log("[Item triggered] #{i.pbThis}'s Flame Orb")
        i.pbBurn(nil,_INTL("{1} was burned by its {2}!",i.pbThis,PBItems.getName(i.item)))
      end
      # Sticky Barb
      if i.hasWorkingItem(:STICKYBARB) && !i.hasWorkingAbility(:MAGICGUARD)
        PBDebug.log("[Item triggered] #{i.pbThis}'s Sticky Barb")
        @scene.pbDamageAnimation(i,0)
        i.pbReduceHP((i.totalhp/8).floor)
        pbDisplay(_INTL("{1} is hurt by its {2}!",i.pbThis,PBItems.getName(i.item)))
      end
      if i.fainted?
        return if !i.pbFaint
      end
    end
    # Slow Start's end message
    if i.hasWorkingAbility(:SLOWSTART) && i.turncount==6
      pbDisplay(_INTL("{1} finally got its act together!",i.pbThis))
    end
    # Form checks
    for i in 0...4
      next if @battlers[i].fainted?
      @battlers[i].pbCheckForm
    end
    pbGainEXP
    pbSwitch
    return if @decision>0
    for i in priority
      next if i.fainted?
      i.pbAbilitiesOnSwitchIn(false)
    end
    # Healing Wish/Lunar Dance - should go here
    # Spikes/Toxic Spikes/Stealth Rock - should go here (in order of their 1st use)
    for i in 0...4
      if @battlers[i].turncount>0 && @battlers[i].hasWorkingAbility(:TRUANT)
        @battlers[i].effects[PBEffects::Truant]=!@battlers[i].effects[PBEffects::Truant]
      end
      if @battlers[i].effects[PBEffects::LockOn]>0   # Also Mind Reader
        @battlers[i].effects[PBEffects::LockOn]-=1
        @battlers[i].effects[PBEffects::LockOnPos]=-1 if @battlers[i].effects[PBEffects::LockOn]==0
      end
      @battlers[i].effects[PBEffects::Flinch]=false
      @battlers[i].effects[PBEffects::FollowMe]=0
      @battlers[i].effects[PBEffects::HelpingHand]=false
      @battlers[i].effects[PBEffects::MagicCoat]=false
      @battlers[i].effects[PBEffects::Snatch]=false
      @battlers[i].effects[PBEffects::Charge]-=1 if @battlers[i].effects[PBEffects::Charge]>0
      @battlers[i].lastHPLost=0
      @battlers[i].tookDamage=false
      @battlers[i].lastAttacker.clear
      @battlers[i].effects[PBEffects::Counter]=-1
      @battlers[i].effects[PBEffects::CounterTarget]=-1
      @battlers[i].effects[PBEffects::MirrorCoat]=-1
      @battlers[i].effects[PBEffects::MirrorCoatTarget]=-1
    end
    for i in 0...2
      if !@sides[i].effects[PBEffects::EchoedVoiceUsed]
        @sides[i].effects[PBEffects::EchoedVoiceCounter]=0
      end
      @sides[i].effects[PBEffects::EchoedVoiceUsed]=false
      @sides[i].effects[PBEffects::MatBlock]= false
      @sides[i].effects[PBEffects::QuickGuard]=false
      @sides[i].effects[PBEffects::WideGuard]=false
      @sides[i].effects[PBEffects::CraftyShield]=false
      @sides[i].effects[PBEffects::Round]=0
    end
    @field.effects[PBEffects::FusionBolt]=false
    @field.effects[PBEffects::FusionFlare]=false
    @field.effects[PBEffects::IonDeluge]=false
    @field.effects[PBEffects::FairyLock]-=1 if @field.effects[PBEffects::FairyLock]>0
    # invalidate stored priority
    @usepriority=false
  end

################################################################################
# End of battle.
################################################################################
  def pbEndOfBattle(canlose=false)
    case @decision
    ##### WIN #####
    when 1
      PBDebug.log("")
      PBDebug.log("***Player won***")
      if @opponent
        @scene.pbTrainerBattleSuccess
        if @opponent.is_a?(Array)
          pbDisplayPaused(_INTL("{1} defeated {2} and {3}!",self.pbPlayer.name,@opponent[0].fullname,@opponent[1].fullname))
        else
          pbDisplayPaused(_INTL("{1} defeated\r\n{2}!",self.pbPlayer.name,@opponent.fullname))
        end
        @scene.pbShowOpponent(0)
        pbDisplayPaused(@endspeech.gsub(/\\[Pp][Nn]/,self.pbPlayer.name))
        if @opponent.is_a?(Array)
          @scene.pbHideOpponent
          @scene.pbShowOpponent(1)
          pbDisplayPaused(@endspeech2.gsub(/\\[Pp][Nn]/,self.pbPlayer.name))
        end
        # Calculate money gained for winning
        if @internalbattle
          tmoney=0
          if @opponent.is_a?(Array)   # Double battles
            maxlevel1=0; maxlevel2=0; limit=pbSecondPartyBegin(1)
            for i in 0...limit
              if @party2[i]
                maxlevel1=@party2[i].level if maxlevel1<@party2[i].level
              end
              if @party2[i+limit]
                maxlevel2=@party2[i+limit].level if maxlevel1<@party2[i+limit].level
              end
            end
            tmoney+=maxlevel1*@opponent[0].moneyEarned
            tmoney+=maxlevel2*@opponent[1].moneyEarned
          else
            maxlevel=0
            for i in @party2
              next if !i
              maxlevel=i.level if maxlevel<i.level
            end
            tmoney+=maxlevel*@opponent.moneyEarned
          end
          # If Amulet Coin/Luck Incense's effect applies, double money earned
          tmoney*=2 if @amuletcoin
          # If Happy Hour's effect applies, double money earned
          tmoney*=2 if @doublemoney
          oldmoney=self.pbPlayer.money
          self.pbPlayer.money+=tmoney
          moneygained=self.pbPlayer.money-oldmoney
          if moneygained>0
            pbDisplayPaused(_INTL("{1} got ${2}\r\nfor winning!",self.pbPlayer.name,pbCommaNumber(tmoney)))
          end
        end
      end
      if @internalbattle && @extramoney>0
        @extramoney*=2 if @amuletcoin
        @extramoney*=2 if @doublemoney
        oldmoney=self.pbPlayer.money
        self.pbPlayer.money+=@extramoney
        moneygained=self.pbPlayer.money-oldmoney
        if moneygained>0
          pbDisplayPaused(_INTL("{1} picked up ${2}!",self.pbPlayer.name,pbCommaNumber(@extramoney)))
        end
      end
      for pkmn in @snaggedpokemon
        pbStorePokemon(pkmn)
        self.pbPlayer.shadowcaught=[] if !self.pbPlayer.shadowcaught
        self.pbPlayer.shadowcaught[pkmn.species]=true
      end
      @snaggedpokemon.clear
    ##### LOSE, DRAW #####
    when 2, 5
      PBDebug.log("")
      PBDebug.log("***Player lost***") if @decision==2
      PBDebug.log("***Player drew with opponent***") if @decision==5
      if @internalbattle
        moneylost=pbMaxLevelFromIndex(0)   # Player's Pokémon only, not partner's
        multiplier=[8,16,24,36,48,64,80,100,120]
        moneylost*=multiplier[[multiplier.length-1,self.pbPlayer.numbadges].min]
        moneylost=self.pbPlayer.money if moneylost>self.pbPlayer.money
        moneylost=0 if $game_switches[NO_MONEY_LOSS]
        oldmoney=self.pbPlayer.money
        self.pbPlayer.money-=moneylost
        lostmoney=oldmoney-self.pbPlayer.money
        if @opponent
          if @opponent.is_a?(Array)
            pbDisplayPaused(_INTL("You lost against {1} and {2}!",@opponent[0].fullname,@opponent[1].fullname))
          else
            pbDisplayPaused(_INTL("You lost against\r\n{1}!",@opponent.fullname))
          end
          if moneylost>0
            pbDisplayPaused(_INTL("You gave ${1} to the winner...",pbCommaNumber(lostmoney)))  
          end
        else
          pbDisplayPaused(_INTL("You have no more Pokémon that can fight!"))
          if moneylost>0
            pbDisplayPaused(_INTL("You panicked and dropped\r\n${1}...",pbCommaNumber(lostmoney)))
          end
        end
        pbDisplayPaused(_INTL("You blacked out!")) if !canlose
      elsif @decision==2
        @scene.pbShowOpponent(0)
        pbDisplayPaused(@endspeechwin.gsub(/\\[Pp][Nn]/,self.pbPlayer.name))
        if @opponent.is_a?(Array)
          @scene.pbHideOpponent
          @scene.pbShowOpponent(1)
          pbDisplayPaused(@endspeechwin2.gsub(/\\[Pp][Nn]/,self.pbPlayer.name))
        end
      end
    end
    # Pass on Pokérus within the party
    infected=[]
    for i in 0...$Trainer.party.length
      if $Trainer.party[i].pokerusStage==1
        infected.push(i)
      end
    end
    if infected.length>=1
      for i in infected
        strain=$Trainer.party[i].pokerusStrain
        if i>0 && $Trainer.party[i-1].pokerusStage==0
          $Trainer.party[i-1].givePokerus(strain) if rand(3)==0
        end
        if i<$Trainer.party.length-1 && $Trainer.party[i+1].pokerusStage==0
          $Trainer.party[i+1].givePokerus(strain) if rand(3)==0
        end
      end
    end
    @scene.pbEndBattle(@decision)
    for i in @battlers
      i.pbResetForm
      if i.hasWorkingAbility(:NATURALCURE)
        i.status=0
      end
    end
    for i in $Trainer.party
      i.setItem(i.itemInitial)
      i.itemInitial=i.itemRecycle=0
      i.belch=false
    end
    return @decision
  end
end