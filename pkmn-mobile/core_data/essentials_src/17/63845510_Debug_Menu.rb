class CommandMenuList
  attr_accessor :currentList

  def initialize
    @commands    = []
    @currentList = "main"
  end

  def add(parent,cmd,name,desc=nil)
    @commands.push([parent,cmd,name,desc])
  end

  def list
    ret = []
    for i in @commands
      ret.push(i[2]) if i[0]==@currentList
    end
    return ret
  end

  def getCommand(index)
    count = 0
    for i in @commands
      if i[0]==@currentList
        return i[1] if count==index
        count += 1
      end
    end
    return nil
  end

  def getDesc(index)
    count = 0
    for i in @commands
      if i[0]==@currentList
        return i[3] if count==index && i[3]
        count += 1
      end
    end
    return "<No description available>"
  end

  def hasSubMenu?(cmd)
    for i in @commands
      return true if i[0]==cmd
    end
    return false
  end

  def getParent
    ret = nil
    for i in @commands
      if i[1]==@currentList
        ret = i[0]; break
      end
    end
    if ret
      count = 0
      for i in @commands
        if i[0]==ret
          return [ret,count] if i[1]==@currentList
          count += 1
        end
      end
      return [ret,0]
    end
    return nil
  end
end


def pbDebugMenuCommands(showall=true)
  commands = CommandMenuList.new
  if showall
    commands.add("main","fieldmenu",_INTL("Field options..."),
       _INTL("Warp to maps, edit switches/variables, use the PC, edit Day Care, etc."))
    commands.add("fieldmenu","warp",_INTL("Warp to Map"),
       _INTL("Instantly warp to another map of your choice."))
    # - Optional coordinates
    commands.add("fieldmenu","refreshmap",_INTL("Refresh Map"),
       _INTL("Make all events on this map, and common events, refresh themselves."))
    commands.add("fieldmenu","switches",_INTL("Switches"),
       _INTL("Edit all Game Switches (except Script Switches)."))
    commands.add("fieldmenu","variables",_INTL("Variables"),
       _INTL("Edit all Game Variables. Can set them to numbers or text."))
    commands.add("fieldmenu","usepc",_INTL("Use PC"),
       _INTL("Use a PC to access Pokémon storage and player's PC."))
    commands.add("fieldmenu","togglewallpapers",_INTL("Toggle Storage Wallpapers"),
       _INTL("Unlock and lock special wallpapers used in Pokémon storage."))
    commands.add("fieldmenu","daycare",_INTL("Day Care"),
       _INTL("View Pokémon in the Day Care and edit them."))
    commands.add("fieldmenu","relicstone",_INTL("Use Relic Stone"),
       _INTL("Shadow Pokémon. Choose a Pokémon to show to the Relic Stone for purification."))
    commands.add("fieldmenu","purifychamber",_INTL("Use Purify Chamber"),
       _INTL("Shadow Pokémon. Open the Purify Chamber for purification."))
  
    commands.add("main","battlemenu",_INTL("Battle options..."),
       _INTL("Start battles, reset this map's trainers, ready rematches, edit roamers, etc."))
    commands.add("battlemenu","testwildbattle",_INTL("Test Wild Battle"),
       _INTL("Start a battle against a wild Pokémon. You choose the species and level."))
    commands.add("battlemenu","testdoublewildbattle",_INTL("Test Double Wild Battle"),
       _INTL("Start a battle against two wild Pokémon. You choose the species and levels."))
    commands.add("battlemenu","testtrainerbattle",_INTL("Test Trainer Battle"),
       _INTL("Start a battle against a defined trainer. You choose which trainer."))
    commands.add("battlemenu","testdoubletrainerbattle",_INTL("Test Double Trainer Battle"),
       _INTL("Start a battle against two defined trainers. You choose which trainers."))
    commands.add("battlemenu","togglelogging",_INTL("Toggle Battle Logging"),
       _INTL("Record debug logs for battles in Data/debuglog.txt."))
    commands.add("battlemenu","resettrainers",_INTL("Reset Map's Trainers"),
       _INTL("Turn off Self Switches A and B for all events with \"Trainer\" in their name."))
    commands.add("battlemenu","readyrematches",_INTL("Ready All Phone Rematches"),
       _INTL("Make all trainers in the phone ready for rematches."))
    commands.add("battlemenu","roamers",_INTL("Roaming Pokémon"),
       _INTL("Toggle and edit all roaming Pokémon."))
  
    commands.add("main","itemsmenu",_INTL("Item options..."),
       _INTL("Give and take items."))
    commands.add("itemsmenu","additem",_INTL("Add Item"),
       _INTL("Choose an item and a quantity of it to add to the Bag."))
    commands.add("itemsmenu","fillbag",_INTL("Fill Bag"),
       _INTL("Add a certain number of every item to the Bag."))
    commands.add("itemsmenu","emptybag",_INTL("Empty Bag"),
       _INTL("Remove all items from the Bag."))
  
    commands.add("main","pokemonmenu",_INTL("Pokémon options..."),
       _INTL("Give Pokémon, heal party, fill/empty PC storage, etc."))
    commands.add("pokemonmenu","addpokemon",_INTL("Add Pokémon"),
       _INTL("Give yourself a Pokémon of a chosen species/level. Goes to PC if party is full."))
    commands.add("pokemonmenu","demoparty",_INTL("Give Demo Party"),
       _INTL("Give yourself 6 preset Pokémon. They overwrite the current party."))
    commands.add("pokemonmenu","healparty",_INTL("Heal Party"),
       _INTL("Fully heal the HP/status/PP of all Pokémon in the party."))
    commands.add("pokemonmenu","quickhatch",_INTL("Quick Hatch"),
       _INTL("Make all eggs in the party require just one more step to hatch."))
    commands.add("pokemonmenu","fillboxes",_INTL("Fill Storage Boxes"),
       _INTL("Add one Pokémon of each species (at Level 50) to storage."))
    commands.add("pokemonmenu","clearboxes",_INTL("Clear Storage Boxes"),
       _INTL("Remove all Pokémon in storage."))
    commands.add("pokemonmenu","openstorage",_INTL("Access Pokémon Storage"),
       _INTL("Opens the Pokémon storage boxes in Organize Boxes mode."))
  
    commands.add("main","playermenu",_INTL("Player options..."),
       _INTL("Set money, badges, Pokédexes, player's appearance and name, etc."))
    commands.add("playermenu","setbadges",_INTL("Set Badges"),
       _INTL("Toggle possession of each Gym Badge."))
    commands.add("playermenu","setmoney",_INTL("Set Money"),
       _INTL("Edit how much money you have."))
    commands.add("playermenu","setcoins",_INTL("Set Coins"),
       _INTL("Edit how many Game Corner Coins you have."))
    commands.add("playermenu","toggleshoes",_INTL("Toggle Running Shoes"),
       _INTL("Toggle possession of running shoes."))
    commands.add("playermenu","togglepokegear",_INTL("Toggle Pokégear"),
       _INTL("Toggle possession of the Pokégear."))
    commands.add("playermenu","dexlists",_INTL("Toggle Pokédex and Dexes"),
       _INTL("Toggle possession of the Pokédex, and edit Regional Dex accessibility."))
    commands.add("playermenu","setplayer",_INTL("Set Player Character"),
       _INTL("Edit the player's character, as defined in \"metadata.txt\"."))
    commands.add("playermenu","changeoutfit",_INTL("Set Player Outfit"),
       _INTL("Edit the player's outfit number."))
    commands.add("playermenu","renameplayer",_INTL("Set Player Name"),
       _INTL("Rename the player."))
    commands.add("playermenu","randomid",_INTL("Randomise Player ID"),
       _INTL("Generate a random new ID for the player."))
  end

  commands.add("main","editorsmenu",_INTL("Information editors..."),
     _INTL("Edit information in the PBS files, terrain tags, battle animations, etc."))
  commands.add("editorsmenu","setmetadata",_INTL("Edit Metadata"),
     _INTL("Edit global and map-specific metadata."))
  commands.add("editorsmenu","mapconnections",_INTL("Edit Map Connections"),
     _INTL("Connect maps using a visual interface. Can also edit map encounters/metadata."))
  commands.add("editorsmenu","terraintags",_INTL("Edit Terrain Tags"),
     _INTL("Edit the terrain tags of tiles in tilesets. Required for tags 8+."))
  commands.add("editorsmenu","setencounters",_INTL("Edit Wild Encounters"),
     _INTL("Edit the wild Pokémon that can be found on maps, and how they are encountered."))
  commands.add("editorsmenu","trainertypes",_INTL("Edit Trainer Types"),
     _INTL("Edit the properties of trainer types."))
  commands.add("editorsmenu","edittrainers",_INTL("Edit Individual Trainers"),
     _INTL("Edit individual trainers, their Pokémon and items."))
  commands.add("editorsmenu","edititems",_INTL("Edit Items"),
     _INTL("Edit item data."))
  commands.add("editorsmenu","editpokemon",_INTL("Edit Pokémon"),
     _INTL("Edit Pokémon species data."))
  commands.add("editorsmenu","editdexes",_INTL("Edit Regional Dexes"),
     _INTL("Create, rearrange and delete Regional Pokédex lists."))
  commands.add("editorsmenu","positionsprites",_INTL("Edit Pokémon Sprite Positions"),
     _INTL("Reposition Pokémon sprites in battle."))
  commands.add("editorsmenu","autopositionsprites",_INTL("Auto-Position All Sprites"),
     _INTL("Automatically reposition all Pokémon sprites in battle. Don't use lightly."))
  commands.add("editorsmenu","animeditor",_INTL("Battle Animation Editor"),
     _INTL("Edit the battle animations."))
  commands.add("editorsmenu","importanims",_INTL("Import All Battle Animations"),
     _INTL("Import all battle animations from the \"Animations\" folder."))
  commands.add("editorsmenu","exportanims",_INTL("Export All Battle Animations"),
     _INTL("Export all battle animations individually to the \"Animations\" folder."))
  
  commands.add("main","othermenu",_INTL("Other options..."),
     _INTL("Mystery Gifts, translations, compile data, etc."))
  commands.add("othermenu","mysterygift",_INTL("Manage Mystery Gifts"),
    _INTL("Edit and enable/disable Mystery Gifts."))
  commands.add("othermenu","extracttext",_INTL("Extract Text"),
    _INTL("Extract all text in the game to a single file for translating."))
  commands.add("othermenu","compiletext",_INTL("Compile Text"),
    _INTL("Import text and converts it into a language file."))
  commands.add("othermenu","compiledata",_INTL("Compile Data"),
    _INTL("Fully compile all data."))
  commands.add("othermenu","debugconsole",_INTL("Debug Console"),
    _INTL("Open the Debug Console."))

  return commands
end

def pbDebugMenuActions(cmd="",sprites=nil,viewport=nil)
  case cmd
  #=============================================================================
  # Field options
  #=============================================================================
  when "warp"
    map = pbWarpToMap
    if map
      pbFadeOutAndHide(sprites)
      Kernel.pbDisposeMessageWindow(sprites["textbox"])
      pbDisposeSpriteHash(sprites)
      viewport.dispose
      if $scene.is_a?(Scene_Map)
        $game_temp.player_new_map_id    = map[0]
        $game_temp.player_new_x         = map[1]
        $game_temp.player_new_y         = map[2]
        $game_temp.player_new_direction = 2
        $scene.transfer_player
        $game_map.refresh
      else
        Kernel.pbCancelVehicles
        $MapFactory.setup(map[0])
        $game_player.moveto(map[1],map[2])
        $game_player.turn_down
        $game_map.update
        $game_map.autoplay
        $game_map.refresh
      end
      return true   # Closes the debug menu to allow the warp
    end
  when "refreshmap"
    $game_map.need_refresh = true
    Kernel.pbMessage(_INTL("The map will refresh."))
  when "switches"
    pbDebugVariables(0)
  when "variables"
    pbDebugVariables(1)
  when "usepc"
    pbPokeCenterPC
  when "togglewallpapers"
    w = $PokemonStorage.allWallpapers
    if w.length<=PokemonStorage::BASICWALLPAPERQTY
      Kernel.pbMessage(_INTL("There are no special wallpapers defined."))
    else
      paperscmd = 0
      unlockarray = $PokemonStorage.unlockedWallpapers
      loop do
        paperscmds = []
        paperscmds.push(_INTL("Unlock all"))
        paperscmds.push(_INTL("Lock all"))
        for i in PokemonStorage::BASICWALLPAPERQTY...w.length
          paperscmds.push(_INTL("{1} {2}",unlockarray[i] ? "[Y]" : "[  ]",w[i]))
        end
        paperscmd = Kernel.pbShowCommands(nil,paperscmds,-1,paperscmd)
        break if paperscmd<0
        if paperscmd==0   # Unlock all
          for i in PokemonStorage::BASICWALLPAPERQTY...w.length
            unlockarray[i] = true
          end
        elsif paperscmd==1   # Lock all
          for i in PokemonStorage::BASICWALLPAPERQTY...w.length
            unlockarray[i] = false
          end
        else
          paperindex = paperscmd-2+PokemonStorage::BASICWALLPAPERQTY
          unlockarray[paperindex] = !$PokemonStorage.unlockedWallpapers[paperindex]
        end
      end
    end
  when "daycare"
    pbDebugDayCare
  when "relicstone"
    pbRelicStone
  when "purifychamber"
    pbPurifyChamber
  #=============================================================================
  # Battle options
  #=============================================================================
  when "testwildbattle"
    species = pbChooseSpeciesList
    if species!=0
      params = ChooseNumberParams.new
      params.setRange(1,PBExperience::MAXLEVEL)
      params.setInitialValue(5)
      params.setCancelValue(0)
      level = Kernel.pbMessageChooseNumber(_INTL("Set the wild {1}'s level.",PBSpecies.getName(species)),params)
      if level>0
        $PokemonTemp.encounterType = -1
        pbWildBattle(species,level)
      end
    end
  when "testdoublewildbattle"
    Kernel.pbMessage(_INTL("Choose the first Pokémon."))
    species1 = pbChooseSpeciesList
    if species1!=0
      params = ChooseNumberParams.new
      params.setRange(1,PBExperience::MAXLEVEL)
      params.setInitialValue(5)
      params.setCancelValue(0)
      level1 = Kernel.pbMessageChooseNumber(_INTL("Set the wild {1}'s level.",PBSpecies.getName(species1)),params)
      if level1>0
        Kernel.pbMessage(_INTL("Choose the second Pokémon."))
        species2 = pbChooseSpeciesList
        if species2!=0
          params = ChooseNumberParams.new
          params.setRange(1,PBExperience::MAXLEVEL)
          params.setInitialValue(5)
          params.setCancelValue(0)
          level2 = Kernel.pbMessageChooseNumber(_INTL("Set the wild {1}'s level.",PBSpecies.getName(species2)),params)
          if level2>0
            $PokemonTemp.encounterType = -1
            pbDoubleWildBattle(species1,level1,species2,level2)
          end
        end
      end
    end
  when "testtrainerbattle"
    battle = pbListScreen(_INTL("SINGLE TRAINER"),TrainerBattleLister.new(0,false))
    if battle
      trainerdata = battle[1]
      pbTrainerBattle(trainerdata[0],trainerdata[1],"...",false,trainerdata[4],true)
    end
  when "testdoubletrainerbattle"
    battle1 = pbListScreen(_INTL("DOUBLE TRAINER 1"),TrainerBattleLister.new(0,false))
    if battle1
      battle2 = pbListScreen(_INTL("DOUBLE TRAINER 2"),TrainerBattleLister.new(0,false))
      if battle2
        trainerdata1 = battle1[1]
        trainerdata2 = battle2[1]
        pbDoubleTrainerBattle(trainerdata1[0],trainerdata1[1],trainerdata1[4],"...",
                              trainerdata2[0],trainerdata2[1],trainerdata2[4],"...",
                              true)
      end
    end
  when "togglelogging"
    $INTERNAL = !$INTERNAL
    Kernel.pbMessage(_INTL("Debug logs for battles will be made in the Data folder.")) if $INTERNAL
    Kernel.pbMessage(_INTL("Debug logs for battles will not be made.")) if !$INTERNAL
  when "resettrainers"
    if $game_map
      for event in $game_map.events.values
        if event.name[/Trainer/]
          $game_self_switches[[$game_map.map_id,event.id,"A"]] = false
          $game_self_switches[[$game_map.map_id,event.id,"B"]] = false
        end
      end
      $game_map.need_refresh = true
      Kernel.pbMessage(_INTL("All Trainers on this map were reset."))
    else
      Kernel.pbMessage(_INTL("This command can't be used here."))
    end
  when "readyrematches"
    if !$PokemonGlobal.phoneNumbers || $PokemonGlobal.phoneNumbers.length==0
      Kernel.pbMessage(_INTL("There are no trainers in the Phone."))
    else
      for i in $PokemonGlobal.phoneNumbers
        if i.length==8 # A trainer with an event
          i[4] = 2
          pbSetReadyToBattle(i)
        end
      end
      Kernel.pbMessage(_INTL("All trainers in the Phone are now ready to rebattle."))
    end
  when "roamers"
    pbDebugRoamers
  #=============================================================================
  # Item options
  #=============================================================================
  when "additem"
    pbListScreenBlock(_INTL("ADD ITEM"),ItemLister.new(0)){|button,item|
      if button==Input::C && item && item>0
        params = ChooseNumberParams.new
        params.setRange(1,BAGMAXPERSLOT)
        params.setInitialValue(1)
        params.setCancelValue(0)
        qty = Kernel.pbMessageChooseNumber(_INTL("Choose the number of items."),params)
        if qty>0
          $PokemonBag.pbStoreItem(item,qty)
          Kernel.pbMessage(_INTL("Gave {1}x {2}.",qty,PBItems.getName(item)))
        end
      end
    }
  when "fillbag"
    params = ChooseNumberParams.new
    params.setRange(1,BAGMAXPERSLOT)
    params.setInitialValue(1)
    params.setCancelValue(0)
    qty = Kernel.pbMessageChooseNumber(_INTL("Choose the number of items."),params)
    if qty>0
      itemconsts = []
      for i in PBItems.constants
        itemconsts.push(PBItems.const_get(i))
      end
      itemconsts.sort!{|a,b| a<=>b }
      for i in itemconsts
        $PokemonBag.pbStoreItem(i,qty)
      end
      Kernel.pbMessage(_INTL("The Bag was filled with {1} of each item.",qty))
    end
  when "emptybag"
    $PokemonBag.clear
    Kernel.pbMessage(_INTL("The Bag was cleared."))
  #=============================================================================
  # Pokémon options
  #=============================================================================
  when "addpokemon"
    species = pbChooseSpeciesList
    if species!=0
      params = ChooseNumberParams.new
      params.setRange(1,PBExperience::MAXLEVEL)
      params.setInitialValue(5)
      params.setCancelValue(0)
      level = Kernel.pbMessageChooseNumber(_INTL("Set the Pokémon's level."),params)
      if level>0
        pbAddPokemon(species,level)
      end
    end
  when "demoparty"
    pbCreatePokemon
    Kernel.pbMessage(_INTL("Filled party with demo Pokémon."))
  when "healparty"
    for i in $Trainer.party
      i.heal
    end
    Kernel.pbMessage(_INTL("Your Pokémon were fully healed."))
  when "quickhatch"
    for pokemon in $Trainer.party
      pokemon.eggsteps = 1 if pokemon.egg?
    end
    Kernel.pbMessage(_INTL("All eggs in your party now require one step to hatch."))
  when "fillboxes"
    $Trainer.formseen     = [] if !$Trainer.formseen
    $Trainer.formlastseen = [] if !$Trainer.formlastseen
    added = 0; completed = true
    dexdata = pbOpenDexData
    formdata = pbLoadFormsData
    for i in 1..PBSpecies.maxValue
      if added>=STORAGEBOXES*30
        completed = false; break
      end
      cname = getConstantName(PBSpecies,i) rescue nil
      next if !cname
      pkmn = PokeBattle_Pokemon.new(i,50,$Trainer)
      $PokemonStorage[(i-1)/$PokemonStorage.maxPokemon(0),
                      (i-1)%$PokemonStorage.maxPokemon(0)] = pkmn
      # Record all forms of this Pokémon as seen and owned
      $Trainer.seen[i]  = true
      $Trainer.owned[i] = true
      $Trainer.formseen[i] = [[],[]]
      formdata[i] = [i] if !formdata[i]
      if formdata[i]
        for form in 0...formdata[i].length
          fSpecies = pbGetFSpeciesFromForm(i,form)
          formname = pbGetMessage(MessageTypes::FormNames,fSpecies)
          if form==0
            pbDexDataOffset(dexdata,i,18)
            genderbyte = dexdata.fgetb
            case genderbyte
            when 0, 254, 255 # Male only, female only, genderless
              gender = (genderbyte==254) ? 1 : 0
              $Trainer.formseen[i][gender][form] = true
              $Trainer.formlastseen[i] = [gender,0]
            else # Both male and female
              $Trainer.formseen[i][0][form] = true
              $Trainer.formseen[i][1][form] = true
              $Trainer.formlastseen[i] = [0,0]
            end
          elsif formname && formname!=""
            $Trainer.formseen[i][0][form] = true
          end
        end
      end
      added += 1
    end
    dexdata.close
    Kernel.pbMessage(_INTL("Storage boxes were filled with one Pokémon of each species."))
    if !completed
      Kernel.pbMessage(_INTL("Note: The number of storage spaces ({1} boxes of 30) is less than the number of species.",STORAGEBOXES))
    end
  when "clearboxes"
    for i in 0...$PokemonStorage.maxBoxes
      for j in 0...$PokemonStorage.maxPokemon(i)
        $PokemonStorage[i,j] = nil
      end
    end
    Kernel.pbMessage(_INTL("The storage boxes were cleared."))
  when "openstorage"
    pbFadeOutIn(99999){
      scene = PokemonStorageScene.new
      screen = PokemonStorageScreen.new(scene,$PokemonStorage)
      screen.pbStartScreen(0)
    }
  #=============================================================================
  # Player options
  #=============================================================================
  when "setbadges"
    badgecmd = 0
    loop do
      badgecmds = []
      badgecmds.push(_INTL("Give all"))
      badgecmds.push(_INTL("Remove all"))
      for i in 0...24
        badgecmds.push(_INTL("{1} Badge {2}",$Trainer.badges[i] ? "[Y]" : "[  ]",i+1))
      end
      badgecmd = Kernel.pbShowCommands(nil,badgecmds,-1,badgecmd)
      break if badgecmd<0
      if badgecmd==0   # Give all
        for i in 0...24; $Trainer.badges[i] = true; end
      elsif badgecmd==1   # Remove all
        for i in 0...24; $Trainer.badges[i] = false; end
      else
        $Trainer.badges[badgecmd-2] = !$Trainer.badges[badgecmd-2]
      end
    end
  when "setmoney"
    params = ChooseNumberParams.new
    params.setMaxDigits(6)
    params.setDefaultValue($Trainer.money)
    $Trainer.money = Kernel.pbMessageChooseNumber(_INTL("Set the player's money."),params)
    Kernel.pbMessage(_INTL("You now have ${1}.",pbCommaNumber($Trainer.money)))
  when "setcoins"
    params = ChooseNumberParams.new
    params.setRange(0,MAXCOINS)
    params.setDefaultValue($PokemonGlobal.coins)
    $PokemonGlobal.coins = Kernel.pbMessageChooseNumber(_INTL("Set the player's Coin amount."),params)
    Kernel.pbMessage(_INTL("You now have {1} Coins.",pbCommaNumber($PokemonGlobal.coins)))
  when "toggleshoes"
    $PokemonGlobal.runningShoes = !$PokemonGlobal.runningShoes
    Kernel.pbMessage(_INTL("Gave Running Shoes.")) if $PokemonGlobal.runningShoes
    Kernel.pbMessage(_INTL("Lost Running Shoes.")) if !$PokemonGlobal.runningShoes
  when "togglepokegear"
    $Trainer.pokegear = !$Trainer.pokegear
    Kernel.pbMessage(_INTL("Gave Pokégear.")) if $Trainer.pokegear
    Kernel.pbMessage(_INTL("Lost Pokégear.")) if !$Trainer.pokegear
  when "dexlists"
    dexescmd = 0
    loop do
      dexescmds = []
      dexescmds.push(_INTL("Have Pokédex: {1}",$Trainer.pokedex ? "[YES]" : "[NO]"))
      d = pbDexNames
      for i in 0...d.length
        name = d[i]
        name = name[0] if name.is_a?(Array)
        dexindex = i
        unlocked = $PokemonGlobal.pokedexUnlocked[dexindex]
        dexescmds.push(_INTL("{1} {2}",unlocked ? "[Y]" : "[  ]",name))
      end
      dexescmd = Kernel.pbShowCommands(nil,dexescmds,-1,dexescmd)
      break if dexescmd<0
      dexindex = dexescmd-1
      if dexindex<0   # Toggle Pokédex ownership
        $Trainer.pokedex = !$Trainer.pokedex
      else   # Toggle Regional Dex accessibility
        if $PokemonGlobal.pokedexUnlocked[dexindex]
          pbLockDex(dexindex)
        else
          pbUnlockDex(dexindex)
        end
      end
    end
  when "setplayer"
    limit = 0
    for i in 0...8
      meta = pbGetMetadata(0,MetadataPlayerA+i)
      if !meta
        limit = i; break
      end
    end
    if limit<=1
      Kernel.pbMessage(_INTL("There is only one player defined."))
    else
      params = ChooseNumberParams.new
      params.setRange(0,limit-1)
      params.setDefaultValue($PokemonGlobal.playerID)
      newid = Kernel.pbMessageChooseNumber(_INTL("Choose the new player character."),params)
      if newid!=$PokemonGlobal.playerID
        pbChangePlayer(newid)
        Kernel.pbMessage(_INTL("The player character was changed."))
      end
    end
  when "changeoutfit"
    oldoutfit = $Trainer.outfit
    params = ChooseNumberParams.new
    params.setRange(0,99)
    params.setDefaultValue(oldoutfit)
    $Trainer.outfit = Kernel.pbMessageChooseNumber(_INTL("Set the player's outfit."),params)
    Kernel.pbMessage(_INTL("Player's outfit was changed.")) if $Trainer.outfit!=oldoutfit
  when "renameplayer"
    trname = pbEnterPlayerName("Your name?",0,PLAYERNAMELIMIT,$Trainer.name)
    if trname=="" && Kernel.pbConfirmMessage(_INTL("Give yourself a default name?"))
      trainertype = pbGetPlayerTrainerType
      gender      = pbGetTrainerTypeGender(trainertype) 
      trname      = pbSuggestTrainerName(gender)
    end
    if trname==""
      Kernel.pbMessage(_INTL("The player's name remained {1}.",$Trainer.name))
    else
      $Trainer.name = trname
      Kernel.pbMessage(_INTL("The player's name was changed to {1}.",$Trainer.name))
    end
  when "randomid"
    $Trainer.id = rand(256)
    $Trainer.id |= rand(256)<<8
    $Trainer.id |= rand(256)<<16
    $Trainer.id |= rand(256)<<24
    Kernel.pbMessage(_INTL("The player's ID was changed to {1} (full ID: {2}).",$Trainer.publicID,$Trainer.id))
  #=============================================================================
  # Information editors
  #=============================================================================
  when "setmetadata"
    pbMetadataScreen(pbDefaultMap)
    pbClearData
  when "mapconnections"
    pbFadeOutIn(99999){ pbConnectionsEditor }
  when "terraintags"
    pbFadeOutIn(99999){ pbTilesetScreen }
  when "setencounters"
    encdata = load_data("Data/encounters.dat")
    oldencdata = Marshal.dump(encdata)
    map = pbDefaultMap
    loop do
      map = pbListScreen(_INTL("SET ENCOUNTERS"),MapLister.new(map))
      break if map<=0
      pbEncounterEditorMap(encdata,map)
    end
    save_data(encdata,"Data/encounters.dat")
    pbSaveEncounterData
    pbClearData
  when "trainertypes"
    pbFadeOutIn(99999){ pbTrainerTypeEditor }
  when "edittrainers"
    pbFadeOutIn(99999){ pbTrainerBattleEditor }
  when "edititems"
    pbFadeOutIn(99999){ pbItemEditor }
  when "editpokemon"
    pbFadeOutIn(99999){ pbPokemonEditor }
  when "editdexes"
    pbFadeOutIn(99999){ pbRegionalDexEditorMain }
  when "positionsprites"
    pbFadeOutIn(99999) {
      sp = SpritePositioner.new
      sps = SpritePositionerScreen.new(sp)
      sps.pbStart
    }
  when "autopositionsprites"
    if Kernel.pbConfirmMessage(_INTL("Are you sure you want to reposition all sprites?"))
      msgwindow = Kernel.pbCreateMessageWindow
      Kernel.pbMessageDisplay(msgwindow,_INTL("Repositioning all sprites. Please wait."),false)
      Graphics.update
      pbAutoPositionAll
      Kernel.pbDisposeMessageWindow(msgwindow)
    end
  when "animeditor"
    pbFadeOutIn(99999){ pbAnimationEditor }
  when "importanims"
    pbImportAllAnimations
  when "exportanims"
    pbExportAllAnimations
  #=============================================================================
  # Other options
  #=============================================================================
  when "mysterygift"
    pbManageMysteryGifts
  when "extracttext"
    pbExtractText
  when "compiletext"
    pbCompileTextUI
  when "compiledata"
    msgwindow=Kernel.pbCreateMessageWindow
    pbCompileAllData(true) {|msg| Kernel.pbMessageDisplay(msgwindow,msg,false) }
    Kernel.pbMessageDisplay(msgwindow,_INTL("All game data was compiled."))
    Kernel.pbDisposeMessageWindow(msgwindow)
  when "debugconsole"
    Console::setup_console
  end
  return false
end

def pbDebugMenu(showall=true)
  commands = pbDebugMenuCommands(showall)
  viewport = Viewport.new(0,0,Graphics.width,Graphics.height)
  viewport.z = 99999
  sprites = {}
  sprites["textbox"] = Kernel.pbCreateMessageWindow
  sprites["textbox"].letterbyletter = false
  sprites["cmdwindow"] = Window_CommandPokemonEx.new(commands.list)
  cmdwindow = sprites["cmdwindow"]
  cmdwindow.x        = 0
  cmdwindow.y        = 0
  cmdwindow.width    = Graphics.width
  cmdwindow.height   = Graphics.height-sprites["textbox"].height
  cmdwindow.viewport = viewport
  cmdwindow.visible  = true
  sprites["textbox"].text = commands.getDesc(cmdwindow.index)
  pbFadeInAndShow(sprites)
  ret = -1
  refresh = true
  loop do
    loop do
      oldindex = cmdwindow.index
      cmdwindow.update
      if refresh || cmdwindow.index!=oldindex
        sprites["textbox"].text = commands.getDesc(cmdwindow.index)
        refresh = false
      end
      Graphics.update
      Input.update
      if Input.trigger?(Input::B)
        parent = commands.getParent
        if parent
          commands.currentList = parent[0]
          cmdwindow.commands = commands.list
          cmdwindow.index = parent[1]
          refresh = true
        else
          ret = -1
          break
        end
      elsif Input.trigger?(Input::C)
        ret = cmdwindow.index
        break
      end
    end
    break if ret<0
    cmd = commands.getCommand(ret)
    if commands.hasSubMenu?(cmd)
      commands.currentList = cmd
      cmdwindow.commands = commands.list
      cmdwindow.index = 0
      refresh = true
    else
      return if pbDebugMenuActions(cmd,sprites,viewport)
    end
  end
  pbFadeOutAndHide(sprites)
  Kernel.pbDisposeMessageWindow(sprites["textbox"])
  pbDisposeSpriteHash(sprites)
  viewport.dispose
end