class PokeBattle_NullBattlePeer
  def pbOnEnteringBattle(battle,pokemon)
  end

  def pbStorePokemon(player,pokemon)
    if player.party.length<6
      player.party[player.party.length]=pokemon
    end
    return -1
  end

  def pbGetStorageCreator()
    return nil
  end

  def pbCurrentBox()
    return -1
  end

  def pbBoxName(box)
    return ""
  end
end



class PokeBattle_RealBattlePeer
  def pbStorePokemon(player,pokemon)
    if player.party.length<6
      player.party[player.party.length]=pokemon
      return -1
    else
      pokemon.heal
      oldcurbox=$PokemonStorage.currentBox
      storedbox=$PokemonStorage.pbStoreCaught(pokemon)
      if storedbox<0
        pbDisplayPaused(_INTL("Can't catch any more..."))
        return oldcurbox
      else
        return storedbox
      end
    end
  end

  def pbGetStorageCreator()
    creator=nil
    if $PokemonGlobal && $PokemonGlobal.seenStorageCreator
      creator=Kernel.pbGetStorageCreator
    end
    return creator
  end

  def pbCurrentBox()
    return $PokemonStorage.currentBox
  end

  def pbBoxName(box)
   return box<0 ? "" : $PokemonStorage[box].name
  end
end



class PokeBattle_BattlePeer
  def self.create
    return PokeBattle_RealBattlePeer.new
  end
end