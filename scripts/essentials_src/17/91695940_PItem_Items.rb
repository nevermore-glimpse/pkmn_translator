#===============================================================================
# Item data
#===============================================================================
ITEMID        = 0
ITEMNAME      = 1
ITEMPLURAL    = 2
ITEMPOCKET    = 3
ITEMPRICE     = 4
ITEMDESC      = 5
ITEMUSE       = 6
ITEMBATTLEUSE = 7
ITEMTYPE      = 8
ITEMMACHINE   = 9

def pbGetPocket(item)
  return $ItemData[item][ITEMPOCKET]
end

def pbGetPrice(item)
  return $ItemData[item][ITEMPRICE]
end

def pbGetMachine(item)
  return $ItemData[item][ITEMMACHINE]
end

def pbIsMachine?(item)
  return pbIsTechnicalMachine?(item) || pbIsHiddenMachine?(item)
end

def pbIsTechnicalMachine?(item)
  return $ItemData[item] && ($ItemData[item][ITEMUSE]==3)
end

def pbIsHiddenMachine?(item)
  return $ItemData[item] && ($ItemData[item][ITEMUSE]==4)
end

# Important items can't be sold, given to hold, or tossed.
def pbIsImportantItem?(item)
  return $ItemData[item] && (pbIsKeyItem?(item) ||
                             pbIsHiddenMachine?(item) ||
                             (INFINITETMS && pbIsTechnicalMachine?(item)))
end

def pbCanHoldItem?(item)
  return !pbIsImportantItem?(item)
end

def pbIsMail?(item)
  return $ItemData[item] && ($ItemData[item][ITEMTYPE]==1 || $ItemData[item][ITEMTYPE]==2)
end

def pbIsSnagBall?(item)
  return $ItemData[item] && ($ItemData[item][ITEMTYPE]==3 ||
                            ($ItemData[item][ITEMTYPE]==4 && $PokemonGlobal.snagMachine))
end

def pbIsPokeBall?(item)
  return $ItemData[item] && ($ItemData[item][ITEMTYPE]==3 || $ItemData[item][ITEMTYPE]==4)
end

def pbIsBerry?(item)
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==5
end

def pbIsKeyItem?(item)
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==6
end

def pbIsEvolutionStone?(item)
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==7
end

def pbIsFossil?(item)
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==8
end

def pbIsApricorn?(item)
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==9
end

def pbIsGem?(item)
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==10
end

def pbIsMulch?(item)
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==11
end

def pbIsMegaStone?(item)   # Does NOT include Red Orb/Blue Orb
  return $ItemData[item] && $ItemData[item][ITEMTYPE]==12
end

def pbCanRegisterItem?(item)
  return ItemHandlers.hasUseInFieldHandler(item)
end

def pbCanUseOnPokemon?(item)
  return ItemHandlers.hasUseOnPokemon(item) || pbIsMachine?(item)
end

def pbIsHiddenMove?(move)
  return false if !$ItemData
  for i in 0...$ItemData.length
    next if !pbIsHiddenMachine?(i)
    atk=pbGetMachine(i)
    return true if move==atk
  end
  return false
end



#===============================================================================
# ItemHandlers
#===============================================================================
class ItemHandlerHash < HandlerHash
  def initialize
    super(:PBItems)
  end
end



module ItemHandlers
  UseFromBag         = ItemHandlerHash.new
  ConfirmUseInField  = ItemHandlerHash.new
  UseInField         = ItemHandlerHash.new
  UseOnPokemon       = ItemHandlerHash.new
  BattleUseOnBattler = ItemHandlerHash.new
  BattleUseOnPokemon = ItemHandlerHash.new
  UseInBattle        = ItemHandlerHash.new
  UseText            = ItemHandlerHash.new

  def self.addUseFromBag(item,proc)
    UseFromBag.add(item,proc)
  end

  def self.addUseInField(item,proc)
    UseInField.add(item,proc)
  end

  def self.addConfirmUseInField(item,proc)
    ConfirmUseInField.add(item,proc)
  end

  def self.addUseOnPokemon(item,proc)
    UseOnPokemon.add(item,proc)
  end

  def self.addBattleUseOnBattler(item,proc)
    BattleUseOnBattler.add(item,proc)
  end

  def self.addBattleUseOnPokemon(item,proc)
    BattleUseOnPokemon.add(item,proc)
  end

  def self.addUseText(item,proc)
    UseText.add(item,proc)
  end

  def self.hasOutHandler(item)                       # Shows "Use" option in Bag
    return UseFromBag[item]!=nil ||
           UseInField[item]!=nil ||
           UseOnPokemon[item]!=nil
  end

  def self.hasUseInFieldHandler(item)           # Shows "Register" option in Bag
    return UseInField[item]!=nil
  end

  def self.hasUseOnPokemon(item)
    return UseOnPokemon[item]!=nil
  end

  def self.hasBattleUseOnBattler(item)
    return BattleUseOnBattler[item]!=nil
  end

  def self.hasBattleUseOnPokemon(item)
    return BattleUseOnPokemon[item]!=nil
  end

  def self.hasUseInBattle(item)
    return UseInBattle[item]!=nil
  end

  def self.hasUseText(item)
    return UseText[item]!=nil
  end

  def self.triggerUseFromBag(item)
    # Return value:
    # 0 - Item not used
    # 1 - Item used, don't end screen
    # 2 - Item used, end screen
    # 3 - Item used, don't end screen, consume item
    # 4 - Item used, end screen, consume item
    if !UseFromBag[item]
      # Check the UseInField handler if present
      return UseInField.trigger(item) if UseInField[item]
      return 0 # item was not used
    else
      UseFromBag.trigger(item)
    end
  end

  def self.triggerConfirmUseInField(item)
    return true if !ConfirmUseInField[item]
    return ConfirmUseInField.trigger(item)
  end

  def self.triggerUseInField(item)
    # Return value:
    # -1 - Item effect not found
    # 0  - Item not used
    # 1  - Item used
    # 3  - Item used, consume item
    return -1 if !UseInField[item]
    return UseInField.trigger(item)
  end

  def self.triggerUseOnPokemon(item,pokemon,scene)
    # Returns whether item was used
    return false if !UseOnPokemon[item]
    return UseOnPokemon.trigger(item,pokemon,scene)
  end

  def self.triggerBattleUseOnBattler(item,battler,scene)
    # Returns whether item was used
    return false if !BattleUseOnBattler[item]
    return BattleUseOnBattler.trigger(item,battler,scene)
  end

  def self.triggerBattleUseOnPokemon(item,pokemon,battler,scene)
    # Returns whether item was used
    return false if !BattleUseOnPokemon[item]
    return BattleUseOnPokemon.trigger(item,pokemon,battler,scene)
  end

  def self.triggerUseInBattle(item,battler,battle)
    # Returns whether item was used
    return if !UseInBattle[item]
    UseInBattle.trigger(item,battler,battle)
  end

  def self.getUseText(item)
    return nil if !UseText[item]
    return UseText.trigger(item)
  end
end



#===============================================================================
# Change a Pokémon's level
#===============================================================================
def pbChangeLevel(pokemon,newlevel,scene)
  newlevel=1 if newlevel<1
  newlevel=PBExperience::MAXLEVEL if newlevel>PBExperience::MAXLEVEL
  if pokemon.level>newlevel
    attackdiff=pokemon.attack
    defensediff=pokemon.defense
    speeddiff=pokemon.speed
    spatkdiff=pokemon.spatk
    spdefdiff=pokemon.spdef
    totalhpdiff=pokemon.totalhp
    pokemon.level=newlevel
    pokemon.calcStats
    scene.pbRefresh
    Kernel.pbMessage(_INTL("{1} was downgraded to Level {2}!",pokemon.name,pokemon.level))
    attackdiff=pokemon.attack-attackdiff
    defensediff=pokemon.defense-defensediff
    speeddiff=pokemon.speed-speeddiff
    spatkdiff=pokemon.spatk-spatkdiff
    spdefdiff=pokemon.spdef-spdefdiff
    totalhpdiff=pokemon.totalhp-totalhpdiff
    pbTopRightWindow(_INTL("Max. HP<r>{1}\r\nAttack<r>{2}\r\nDefense<r>{3}\r\nSp. Atk<r>{4}\r\nSp. Def<r>{5}\r\nSpeed<r>{6}",
       totalhpdiff,attackdiff,defensediff,spatkdiff,spdefdiff,speeddiff))
    pbTopRightWindow(_INTL("Max. HP<r>{1}\r\nAttack<r>{2}\r\nDefense<r>{3}\r\nSp. Atk<r>{4}\r\nSp. Def<r>{5}\r\nSpeed<r>{6}",
       pokemon.totalhp,pokemon.attack,pokemon.defense,pokemon.spatk,pokemon.spdef,pokemon.speed))
  elsif pokemon.level==newlevel
    Kernel.pbMessage(_INTL("{1}'s level remained unchanged.",pokemon.name))
  else
    attackdiff=pokemon.attack
    defensediff=pokemon.defense
    speeddiff=pokemon.speed
    spatkdiff=pokemon.spatk
    spdefdiff=pokemon.spdef
    totalhpdiff=pokemon.totalhp
    oldlevel=pokemon.level
    pokemon.level=newlevel
    pokemon.changeHappiness("levelup")
    pokemon.calcStats
    scene.pbRefresh
    Kernel.pbMessage(_INTL("{1} was elevated to Level {2}!",pokemon.name,pokemon.level))
    attackdiff=pokemon.attack-attackdiff
    defensediff=pokemon.defense-defensediff
    speeddiff=pokemon.speed-speeddiff
    spatkdiff=pokemon.spatk-spatkdiff
    spdefdiff=pokemon.spdef-spdefdiff
    totalhpdiff=pokemon.totalhp-totalhpdiff
    pbTopRightWindow(_INTL("Max. HP<r>+{1}\r\nAttack<r>+{2}\r\nDefense<r>+{3}\r\nSp. Atk<r>+{4}\r\nSp. Def<r>+{5}\r\nSpeed<r>+{6}",
       totalhpdiff,attackdiff,defensediff,spatkdiff,spdefdiff,speeddiff))
    pbTopRightWindow(_INTL("Max. HP<r>{1}\r\nAttack<r>{2}\r\nDefense<r>{3}\r\nSp. Atk<r>{4}\r\nSp. Def<r>{5}\r\nSpeed<r>{6}",
       pokemon.totalhp,pokemon.attack,pokemon.defense,pokemon.spatk,pokemon.spdef,pokemon.speed))
    movelist=pokemon.getMoveList
    for i in movelist
      if i[0]==pokemon.level          # Learned a new move
        pbLearnMove(pokemon,i[1],true)
      end
    end
    newspecies=pbCheckEvolution(pokemon)
    if newspecies>0
      pbFadeOutInWithMusic(99999){
         evo=PokemonEvolutionScene.new
         evo.pbStartScreen(pokemon,newspecies)
         evo.pbEvolution
         evo.pbEndScreen
      }
    end
  end
end

def pbTopRightWindow(text)
  window=Window_AdvancedTextPokemon.new(text)
  window.z=99999
  window.width=198
  window.y=0
  window.x=Graphics.width-window.width
  pbPlayDecisionSE()
  loop do
    Graphics.update
    Input.update
    window.update
    if Input.trigger?(Input::C)
      break
    end
  end
  window.dispose
end

#===============================================================================
# Restore HP
#===============================================================================
def pbItemRestoreHP(pokemon,restorehp)
  newhp=pokemon.hp+restorehp
  newhp=pokemon.totalhp if newhp>pokemon.totalhp
  hpgain=newhp-pokemon.hp
  pokemon.hp=newhp
  return hpgain
end

def pbHPItem(pokemon,restorehp,scene)
  if pokemon.hp<=0 || pokemon.hp==pokemon.totalhp || pokemon.egg?
    scene.pbDisplay(_INTL("It won't have any effect."))
    return false
  end
  hpgain=pbItemRestoreHP(pokemon,restorehp)
  scene.pbRefresh
  scene.pbDisplay(_INTL("{1}'s HP was restored by {2} points.",pokemon.name,hpgain))
  return true
end

def pbBattleHPItem(pokemon,battler,restorehp,scene)
  if pokemon.hp<=0 || pokemon.hp==pokemon.totalhp || pokemon.egg?
    scene.pbDisplay(_INTL("But it had no effect!"))
    return false
  end
  if battler
    hpgain = battler.pbRecoverHP(restorehp)
  else
    hpgain = pbItemRestoreHP(pokemon,restorehp)
  end
  scene.pbDisplay(_INTL("{1}'s HP was restored.",pokemon.name))
  return true
end

#===============================================================================
# Restore PP
#===============================================================================
def pbRestorePP(pokemon,move,pp)
  return 0 if pokemon.moves[move].id==0
  return 0 if pokemon.moves[move].totalpp==0
  newpp=pokemon.moves[move].pp+pp
  if newpp>pokemon.moves[move].totalpp
    newpp=pokemon.moves[move].totalpp
  end
  oldpp=pokemon.moves[move].pp
  pokemon.moves[move].pp=newpp
  return newpp-oldpp
end

def pbBattleRestorePP(pokemon,battler,move,pp)
  ret=pbRestorePP(pokemon,move,pp)
  if ret>0
    battler.pbSetPP(battler.moves[move],pokemon.moves[move].pp) if battler
  end
  return ret
end

#===============================================================================
# Change EVs
#===============================================================================
def pbJustRaiseEffortValues(pokemon,ev,evgain)
  totalev=0
  for i in 0...6
    totalev+=pokemon.ev[i]
  end
  if totalev+evgain>PokeBattle_Pokemon::EVLIMIT
    evgain=PokeBattle_Pokemon::EVLIMIT-totalev
  end
  if pokemon.ev[ev]+evgain>PokeBattle_Pokemon::EVSTATLIMIT
    evgain=PokeBattle_Pokemon::EVSTATLIMIT-pokemon.ev[ev]
  end
  if evgain>0
    pokemon.ev[ev]+=evgain
    pokemon.calcStats
  end
  return evgain
end

def pbRaiseEffortValues(pokemon,ev,evgain=10,evlimit=true)
  return 0 if evlimit && pokemon.ev[ev]>=100
  totalev=0
  for i in 0...6
    totalev+=pokemon.ev[i]
  end
  if totalev+evgain>PokeBattle_Pokemon::EVLIMIT
    evgain=PokeBattle_Pokemon::EVLIMIT-totalev
  end
  if pokemon.ev[ev]+evgain>PokeBattle_Pokemon::EVSTATLIMIT
    evgain=PokeBattle_Pokemon::EVSTATLIMIT-pokemon.ev[ev]
  end
  if evlimit && pokemon.ev[ev]+evgain>100
    evgain=100-pokemon.ev[ev]
  end
  if evgain>0
    pokemon.ev[ev]+=evgain
    pokemon.calcStats
  end
  return evgain
end

def pbRaiseHappinessAndLowerEV(pokemon,scene,ev,messages)
  h=(pokemon.happiness<255)
  e=(pokemon.ev[ev]>0)
  if !h && !e
    scene.pbDisplay(_INTL("It won't have any effect."))
    return false
  end
  if h
    pokemon.changeHappiness("evberry")
  end
  if e
    pokemon.ev[ev]-=10
    pokemon.ev[ev]=0 if pokemon.ev[ev]<0
    pokemon.calcStats
  end
  scene.pbRefresh
  scene.pbDisplay(messages[2-(h ? 0 : 1)-(e ? 0 : 2)])
  return true
end

#===============================================================================
# Decide whether the player is able to ride/dismount their Bicycle
#===============================================================================
def pbBikeCheck
  if $PokemonGlobal.surfing ||
     (!$PokemonGlobal.bicycle && PBTerrain.onlyWalk?(pbGetTerrainTag))
    Kernel.pbMessage(_INTL("Can't use that here."))
    return false
  end
  if $game_player.pbHasDependentEvents?
    Kernel.pbMessage(_INTL("It can't be used when you have someone with you."))
    return false
  end
  if $PokemonGlobal.bicycle
    if pbGetMetadata($game_map.map_id,MetadataBicycleAlways)
      Kernel.pbMessage(_INTL("You can't dismount your Bike here."))
      return false
    end
    return true
  else
    val=pbGetMetadata($game_map.map_id,MetadataBicycle)
    val=pbGetMetadata($game_map.map_id,MetadataOutdoor) if val==nil
    if !val
      Kernel.pbMessage(_INTL("Can't use that here."))
      return false
    end
    return true
  end
end

#===============================================================================
# Find the closest hidden item (for Iremfinder)
#===============================================================================
def pbClosestHiddenItem
  result = []
  playerX=$game_player.x
  playerY=$game_player.y
  for event in $game_map.events.values
    next if event.name!="HiddenItem"
    next if (playerX-event.x).abs>=8
    next if (playerY-event.y).abs>=6
    next if $game_self_switches[[$game_map.map_id,event.id,"A"]]
    result.push(event)
  end
  return nil if result.length==0
  ret=nil
  retmin=0
  for event in result
    dist=(playerX-event.x).abs+(playerY-event.y).abs
    if !ret || retmin>dist
      ret=event
      retmin=dist
    end
  end
  return ret
end

#===============================================================================
# Teach and forget a move
#===============================================================================
def pbLearnMove(pokemon,move,ignoreifknown=false,bymachine=false,&block)
  return false if !pokemon
  movename=PBMoves.getName(move)
  if pokemon.egg? && !$DEBUG
    Kernel.pbMessage(_INTL("Eggs can't be taught any moves."),&block)
    return false
  end
  if pokemon.respond_to?("isShadow?") && pokemon.isShadow?
    Kernel.pbMessage(_INTL("Shadow Pokémon can't be taught any moves."),&block)
    return false
  end
  pkmnname=pokemon.name
  for i in 0...4
    if pokemon.moves[i].id==move
      Kernel.pbMessage(_INTL("{1} already knows {2}.",pkmnname,movename),&block) if !ignoreifknown
      return false
    end
    if pokemon.moves[i].id==0
      pokemon.moves[i]=PBMove.new(move)
      Kernel.pbMessage(_INTL("\\se[]{1} learned {2}!\\se[Pkmn move learnt]",pkmnname,movename),&block)
      return true
    end
  end
  loop do
    Kernel.pbMessage(_INTL("{1} wants to learn {2}, but it already knows four moves.\1",pkmnname,movename),&block) if !bymachine
    Kernel.pbMessage(_INTL("Please choose a move that will be replaced with {1}.",movename),&block)
    forgetmove=pbForgetMove(pokemon,move)
    if forgetmove>=0
      oldmovename=PBMoves.getName(pokemon.moves[forgetmove].id)
      oldmovepp=pokemon.moves[forgetmove].pp
      pokemon.moves[forgetmove]=PBMove.new(move) # Replaces current/total PP
      pokemon.moves[forgetmove].pp=[oldmovepp,pokemon.moves[forgetmove].totalpp].min if bymachine
      Kernel.pbMessage(_INTL("1,\\wt[16] 2, and\\wt[16]...\\wt[16] ...\\wt[16] ... Ta-da!\\se[Battle ball drop]\1"),&block)
      Kernel.pbMessage(_INTL("{1} forgot how to use {2}.\\nAnd...\1",pkmnname,oldmovename),&block)
      Kernel.pbMessage(_INTL("\\se[]{1} learned {2}!\\se[Pkmn move learnt]",pkmnname,movename),&block)
      return true
    elsif Kernel.pbConfirmMessage(_INTL("Give up on learning {1}?",movename),&block)
      Kernel.pbMessage(_INTL("{1} did not learn {2}.",pkmnname,movename),&block)
      return false
    end
  end
end

def pbForgetMove(pokemon,moveToLearn)
  ret = -1
  pbFadeOutIn(99999){
     scene = PokemonSummary_Scene.new
     screen = PokemonSummaryScreen.new(scene)
     ret = screen.pbStartForgetScreen([pokemon],0,moveToLearn)
  }
  return ret
end

def pbSpeciesCompatible?(species,move)
  ret=false
  return false if species<=0
  data=load_data("Data/tm.dat")
  return false if !data[move]
  return data[move].any? {|item| item==species }
end

#===============================================================================
# Use an item from the Bag and/or on a Pokémon
#===============================================================================
def pbUseItem(bag,item,bagscene=nil)
  found=false
  if $ItemData[item][ITEMUSE]==3 || $ItemData[item][ITEMUSE]==4    # TM or HM
    if $Trainer.pokemonCount==0
      Kernel.pbMessage(_INTL("There is no Pokémon."))
      return 0
    end
    machine=pbGetMachine(item)
    return 0 if machine==nil
    movename=PBMoves.getName(machine)
    Kernel.pbMessage(_INTL("\\se[PC access]You booted up {1}.\1",PBItems.getName(item)))
    if !Kernel.pbConfirmMessage(_INTL("Do you want to teach {1} to a Pokémon?",movename))
      return 0
    elsif pbMoveTutorChoose(machine,nil,true)
      bag.pbDeleteItem(item) if pbIsTechnicalMachine?(item) && !INFINITETMS
      return 1
    else
      return 0
    end
  elsif $ItemData[item][ITEMUSE]==1 || $ItemData[item][ITEMUSE]==5 # Item is usable on a Pokémon
    if $Trainer.pokemonCount==0
      Kernel.pbMessage(_INTL("There is no Pokémon."))
      return 0
    end
    ret=false
    annot=nil
    if pbIsEvolutionStone?(item)
      annot=[]
      for pkmn in $Trainer.party
        elig=(pbCheckEvolution(pkmn,item)>0)
        annot.push(elig ? _INTL("ABLE") : _INTL("NOT ABLE"))
      end
    end
    pbFadeOutIn(99999){
      scene = PokemonParty_Scene.new
      screen = PokemonPartyScreen.new(scene,$Trainer.party)
      screen.pbStartScene(_INTL("Use on which Pokémon?"),false,annot)
      loop do
        scene.pbSetHelpText(_INTL("Use on which Pokémon?"))
        chosen=screen.pbChoosePokemon
        if chosen>=0
          pokemon=$Trainer.party[chosen]
          if pbCheckUseOnPokemon(item,pokemon,screen)
            ret=ItemHandlers.triggerUseOnPokemon(item,pokemon,screen)
            if ret && $ItemData[item][ITEMUSE]==1 # Usable on Pokémon, consumed
              bag.pbDeleteItem(item)
            end
            if !bag.pbHasItem?(item)
              Kernel.pbMessage(_INTL("You used your last {1}.",PBItems.getName(item)))
              break
            end
          end
        else
          ret=false
          break
        end
      end
      screen.pbEndScene
      bagscene.pbRefresh if bagscene
    }
    return ret ? 1 : 0
  elsif $ItemData[item][ITEMUSE]==2 # Item is usable from bag
    intret=ItemHandlers.triggerUseFromBag(item)
    case intret
    when 0; return 0
    when 1; return 1 # Item used
    when 2; return 2 # Item used, end screen
    when 3; bag.pbDeleteItem(item); return 1 # Item used, consume item
    when 4; bag.pbDeleteItem(item); return 2 # Item used, end screen and consume item
    else; Kernel.pbMessage(_INTL("Can't use that here.")); return 0
    end
  else
    Kernel.pbMessage(_INTL("Can't use that here."))
    return 0
  end
end

# Only called when in the party screen and having chosen an item to be used on
# the selected Pokémon
def pbUseItemOnPokemon(item,pokemon,scene)
  if $ItemData[item][ITEMUSE]==3 || $ItemData[item][ITEMUSE]==4    # TM or HM
    machine=pbGetMachine(item)
    return false if machine==nil
    movename=PBMoves.getName(machine)
    if (pokemon.isShadow? rescue false)
      Kernel.pbMessage(_INTL("Shadow Pokémon can't be taught any moves."))
    elsif !pokemon.isCompatibleWithMove?(machine)
      Kernel.pbMessage(_INTL("{1} can't learn {2}.",pokemon.name,movename))
    else
      Kernel.pbMessage(_INTL("\\se[PC access]You booted up {1}.\1",PBItems.getName(item)))
      if Kernel.pbConfirmMessage(_INTL("Do you want to teach {1} to {2}?",movename,pokemon.name))
        if pbLearnMove(pokemon,machine,false,true)
          $PokemonBag.pbDeleteItem(item) if pbIsTechnicalMachine?(item) && !INFINITETMS
          return true
        end
      end
    end
    return false
  else
    ret=ItemHandlers.triggerUseOnPokemon(item,pokemon,scene)
    scene.pbClearAnnotations
    scene.pbHardRefresh
    if ret && $ItemData[item][ITEMUSE]==1 # Usable on Pokémon, consumed
      $PokemonBag.pbDeleteItem(item)
    end
    if !$PokemonBag.pbHasItem?(item)
      Kernel.pbMessage(_INTL("You used your last {1}.",PBItems.getName(item)))
    end
    return ret
  end
  Kernel.pbMessage(_INTL("Can't use that on {1}.",pokemon.name))
  return false
end

def Kernel.pbUseKeyItemInField(item)
  ret = ItemHandlers.triggerUseInField(item)
  if ret==-1 # Item effect not found
    Kernel.pbMessage(_INTL("Can't use that here."))
  elsif ret==3 # Item was used and consumed
    $PokemonBag.pbDeleteItem(item)
  end
  return (ret!=-1 && ret!=0)
end

def pbConsumeItemInBattle(bag,item)
  if item!=0 && $ItemData[item][ITEMBATTLEUSE]!=3 &&
                $ItemData[item][ITEMBATTLEUSE]!=4 &&
                $ItemData[item][ITEMBATTLEUSE]!=0
    # Delete the item just used from stock
    $PokemonBag.pbDeleteItem(item)
  end
end

def pbUseItemMessage(item)
  itemname = PBItems.getName(item)
  if ['a','e','i','o','u'].include?(itemname[0,1].downcase)
    Kernel.pbMessage(_INTL("You used an {1}.",itemname))
  else
    Kernel.pbMessage(_INTL("You used a {1}.",itemname))
  end
end

def pbCheckUseOnPokemon(item,pokemon,screen)
  return pokemon && !pokemon.egg?
end

#===============================================================================
# Give an item to a Pokémon to hold, and take a held item from a Pokémon
#===============================================================================
def pbGiveItemToPokemon(item,pokemon,scene,pkmnid=0)
  newitemname = PBItems.getName(item)
  if pokemon.egg?
    scene.pbDisplay(_INTL("Eggs can't hold items."))
    return false
  elsif pokemon.mail
    scene.pbDisplay(_INTL("{1}'s mail must be removed before giving it an item.",pokemon.name))
    return false if !pbTakeItemFromPokemon(pokemon,scene)
  end
  if pokemon.hasItem?
    olditemname = PBItems.getName(pokemon.item)
    if isConst?(pokemon.item,PBItems,:LEFTOVERS)
      scene.pbDisplay(_INTL("{1} is already holding some {2}.\1",pokemon.name,olditemname))
    elsif ['a','e','i','o','u'].include?(newitemname[0,1].downcase)
      scene.pbDisplay(_INTL("{1} is already holding an {2}.\1",pokemon.name,olditemname))
    else
      scene.pbDisplay(_INTL("{1} is already holding a {2}.\1",pokemon.name,olditemname))
    end
    if scene.pbConfirm(_INTL("Would you like to switch the two items?"))
      $PokemonBag.pbDeleteItem(item)
      if !$PokemonBag.pbStoreItem(pokemon.item)
        if !$PokemonBag.pbStoreItem(item)
          raise _INTL("Could't re-store deleted item in Bag somehow")
        end
        scene.pbDisplay(_INTL("The Bag is full. The Pokémon's item could not be removed."))
      else
        if pbIsMail?(item)
          if pbWriteMail(item,pokemon,pkmnid,scene)
            pokemon.setItem(item)
            scene.pbDisplay(_INTL("Took the {1} from {2} and gave it the {3}.",olditemname,pokemon.name,newitemname))
            return true
          else
            if !$PokemonBag.pbStoreItem(item)
              raise _INTL("Couldn't re-store deleted item in Bag somehow")
            end
          end
        else
          pokemon.setItem(item)
          scene.pbDisplay(_INTL("Took the {1} from {2} and gave it the {3}.",olditemname,pokemon.name,newitemname))
          return true
        end
      end
    end
  else
    if !pbIsMail?(item) || pbWriteMail(item,pokemon,pkmnid,scene)
      $PokemonBag.pbDeleteItem(item)
      pokemon.setItem(item)
      scene.pbDisplay(_INTL("{1} is now holding the {2}.",pokemon.name,newitemname))
      return true
    end
  end
  return false
end

def pbTakeItemFromPokemon(pokemon,scene)
  ret = false
  if !pokemon.hasItem?
    scene.pbDisplay(_INTL("{1} isn't holding anything.",pokemon.name))
  elsif !$PokemonBag.pbCanStore?(pokemon.item)
    scene.pbDisplay(_INTL("The Bag is full. The Pokémon's item could not be removed."))
  elsif pokemon.mail
    if scene.pbConfirm(_INTL("Save the removed mail in your PC?"))
      if !pbMoveToMailbox(pokemon)
        scene.pbDisplay(_INTL("Your PC's Mailbox is full."))
      else
        scene.pbDisplay(_INTL("The mail was saved in your PC."))
        pokemon.setItem(0)
        ret = true
      end
    elsif scene.pbConfirm(_INTL("If the mail is removed, its message will be lost. OK?"))
      $PokemonBag.pbStoreItem(pokemon.item)
      itemname = PBItems.getName(pokemon.item)
      scene.pbDisplay(_INTL("Received the {1} from {2}.",itemname,pokemon.name))
      pokemon.setItem(0)
      pokemon.mail = nil
      ret = true
    end
  else
    $PokemonBag.pbStoreItem(pokemon.item)
    itemname = PBItems.getName(pokemon.item)
    scene.pbDisplay(_INTL("Received the {1} from {2}.",itemname,pokemon.name))
    pokemon.setItem(0)
    ret = true
  end
  return ret
end

#===============================================================================
# Choose an item from the Bag
#===============================================================================
def Kernel.pbChooseItem(var=0,*args)
  ret = 0
  pbFadeOutIn(99999){ 
    scene = PokemonBag_Scene.new
    screen = PokemonBagScreen.new(scene,$PokemonBag)
    ret = screen.pbChooseItemScreen
  }
  $game_variables[var] = ret if var>0
  return ret
end

def pbChooseApricorn(var=0)
  ret = 0
  pbFadeOutIn(99999){
    scene = PokemonBag_Scene.new
    screen = PokemonBagScreen.new(scene,$PokemonBag)
    ret = screen.pbChooseItemScreen(Proc.new{|item| pbIsApricorn?(item) })
  }
  $game_variables[var] = ret if var>0
  return ret
end

def pbChooseFossil(var=0)
  ret = 0
  pbFadeOutIn(99999){
    scene = PokemonBag_Scene.new
    screen = PokemonBagScreen.new(scene,$PokemonBag)
    ret = screen.pbChooseItemScreen(Proc.new{|item| pbIsFossil?(item) })
  }
  $game_variables[var] = ret if var>0
  return ret
end

# Shows a list of items to choose from, with the chosen item's ID being stored
# in the given Global Variable. Only items which the player has are listed.
def pbChooseItemFromList(message,variable,*args)
  commands = []
  itemid   = []
  for item in args
    if hasConst?(PBItems,item)
      id = getConst(PBItems,item)
      if $PokemonBag.pbHasItem?(id)
        commands.push(PBItems.getName(id))
        itemid.push(id)
      end
    end
  end
  if commands.length==0
    $game_variables[variable] = 0
    return 0
  end
  commands.push(_INTL("Cancel"))
  itemid.push(0)
  ret = Kernel.pbMessage(message,commands,-1)
  if ret<0 || ret>=commands.length-1
    $game_variables[variable] = -1
    return -1
  else
    $game_variables[variable] = itemid[ret]
    return itemid[ret]
  end
end