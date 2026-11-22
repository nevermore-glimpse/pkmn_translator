#===============================================================================
#
#===============================================================================
module DebugMenuCommands
  @@commands = HandlerHashBasic.new

  def self.register(option, hash)
    @@commands.add(option, hash)
  end

  def self.registerIf(condition, hash)
    @@commands.addIf(condition, hash)
  end

  def self.copy(option, *new_options)
    @@commands.copy(option, *new_options)
  end

  def self.each
    @@commands.each { |key, hash| yield key, hash }
  end

  def self.hasFunction?(option, function)
    option_hash = @@commands[option]
    return option_hash && option_hash.keys.include?(function)
  end

  def self.getFunction(option, function)
    option_hash = @@commands[option]
    return (option_hash && option_hash[function]) ? option_hash[function] : nil
  end

  def self.call(function, option, *args)
    option_hash = @@commands[option]
    return nil if !option_hash || !option_hash[function]
    return (option_hash[function].call(*args) == true)
  end
end

#===============================================================================
# Field options
#===============================================================================
DebugMenuCommands.register("fieldmenu", {
  "parent"      => "main",
  "name"        => _INTL("场地选项…"),
  "description" => _INTL("传送至地图、编辑开关/变量、使用电脑、编辑培育屋等。")
})

DebugMenuCommands.register("warp", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("传送至地图"),
  "description" => _INTL("立即传送到你选择的另一张地图。"),
  "effect"      => proc { |sprites, viewport|
    map = pbWarpToMap
    if map
      pbFadeOutAndHide(sprites)
      pbDisposeMessageWindow(sprites["textbox"])
      pbDisposeSpriteHash(sprites)
      viewport.dispose
      if $scene.is_a?(Scene_Map)
        $game_temp.player_new_map_id    = map[0]
        $game_temp.player_new_x         = map[1]
        $game_temp.player_new_y         = map[2]
        $game_temp.player_new_direction = 2
        $scene.transfer_player
      else
        pbCancelVehicles
        $MapFactory.setup(map[0])
        $game_player.moveto(map[1], map[2])
        $game_player.turn_down
        $game_map.update
        $game_map.autoplay
      end
      $game_map.refresh
      next true   # Closes the debug menu to allow the warp
    end
  }
})

DebugMenuCommands.register("refreshmap", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("刷新地图"),
  "description" => _INTL("让本图所有事件及公共事件自行刷新。"),
  "effect"      => proc {
    $game_map.need_refresh = true
    pbMessage(_INTL("地图将刷新。"))
  }
})

DebugMenuCommands.register("switches", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("开关"),
  "description" => _INTL("编辑所有游戏开关（脚本开关除外）。"),
  "effect"      => proc {
    pbDebugVariables(0)
  }
})

DebugMenuCommands.register("variables", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("变量"),
  "description" => _INTL("编辑所有游戏变量，可设为数字或文本。"),
  "effect"      => proc {
    pbDebugVariables(1)
  }
})

DebugMenuCommands.register("usepc", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("使用电脑"),
  "description" => _INTL("使用电脑访问宝可梦寄存系统与玩家电脑。"),
  "effect"      => proc {
    pbPokeCenterPC
  }
})

DebugMenuCommands.register("togglewallpapers", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("切换寄存壁纸"),
  "description" => _INTL("解锁/锁定宝可梦寄存系统使用的特殊壁纸。"),
  "effect"      => proc {
    w = $PokemonStorage.allWallpapers
    if w.length <= PokemonStorage::BASICWALLPAPERQTY
      pbMessage(_INTL("没有定义特殊壁纸。"))
    else
      paperscmd = 0
      unlockarray = $PokemonStorage.unlockedWallpapers
      loop do
        paperscmds = []
        paperscmds.push(_INTL("全部解锁"))
        paperscmds.push(_INTL("全部锁定"))
        for i in PokemonStorage::BASICWALLPAPERQTY...w.length
          paperscmds.push(_INTL("{1} {2}", unlockarray[i] ? "[Y]" : "[  ]", w[i]))
        end
        paperscmd = pbShowCommands(nil, paperscmds, -1, paperscmd)
        break if paperscmd < 0
        if paperscmd == 0   # Unlock all
          for i in PokemonStorage::BASICWALLPAPERQTY...w.length
            unlockarray[i] = true
          end
        elsif paperscmd == 1   # Lock all
          for i in PokemonStorage::BASICWALLPAPERQTY...w.length
            unlockarray[i] = false
          end
        else
          paperindex = paperscmd - 2 + PokemonStorage::BASICWALLPAPERQTY
          unlockarray[paperindex] = !$PokemonStorage.unlockedWallpapers[paperindex]
        end
      end
    end
  }
})

DebugMenuCommands.register("daycare", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("培育屋"),
  "description" => _INTL("查看并编辑培育屋中的宝可梦。"),
  "effect"      => proc {
    pbDebugDayCare
  }
})

DebugMenuCommands.register("relicstone", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("使用古代石"),
  "description" => _INTL("暗影宝可梦。选择一只带到古代石进行净化。"),
  "effect"      => proc {
    pbRelicStone
  }
})

DebugMenuCommands.register("purifychamber", {
  "parent"      => "fieldmenu",
  "name"        => _INTL("使用净化室"),
  "description" => _INTL("暗影宝可梦。打开净化室进行净化。"),
  "effect"      => proc {
    pbPurifyChamber
  }
})

#===============================================================================
# Battle options
#===============================================================================
DebugMenuCommands.register("battlemenu", {
  "parent"      => "main",
  "name"        => _INTL("战斗选项…"),
  "description" => _INTL("开始对战、重置本图训练家、准备再战、编辑游走宝可梦等。")
})

DebugMenuCommands.register("testwildbattle", {
  "parent"      => "battlemenu",
  "name"        => _INTL("测试野生对战"),
  "description" => _INTL("与一只野生宝可梦进行单场对战，种类/等级自选。"),
  "effect"      => proc {
    species = pbChooseSpeciesList
    if species
      params = ChooseNumberParams.new
      params.setRange(1, GameData::GrowthRate.max_level)
      params.setInitialValue(5)
      params.setCancelValue(0)
      level = pbMessageChooseNumber(_INTL("设置野生 {1} 的等级。",
         GameData::Species.get(species).name), params)
      if level > 0
        $PokemonTemp.encounterType = nil
        pbWildBattle(species, level)
      end
    end
    next false
  }
})

DebugMenuCommands.register("testwildbattleadvanced", {
  "parent"      => "battlemenu",
  "name"        => _INTL("测试野生对战（高级）"),
  "description" => _INTL("与 1 只或多只野生宝可梦开战，战斗规模自选。"),
  "effect"      => proc {
    pkmn = []
    size0 = 1
    pkmnCmd = 0
    loop do
      pkmnCmds = []
      pkmn.each { |p| pkmnCmds.push(sprintf("%s Lv.%d", p.name, p.level)) }
      pkmnCmds.push(_INTL("【添加宝可梦】"))
      pkmnCmds.push(_INTL("【设置我方一侧的尺寸】"))
      pkmnCmds.push(_INTL("[开始 {1}v{2} 战斗]", size0, pkmn.length))
      pkmnCmd = pbShowCommands(nil, pkmnCmds, -1, pkmnCmd)
      break if pkmnCmd < 0
      if pkmnCmd == pkmnCmds.length - 1      # Start battle
        if pkmn.length == 0
          pbMessage(_INTL("没有选择宝可梦，无法开始战斗。"))
          next
        end
        setBattleRule(sprintf("%dv%d", size0, pkmn.length))
        $PokemonTemp.encounterType = nil
        pbWildBattleCore(*pkmn)
        break
      elsif pkmnCmd == pkmnCmds.length - 2   # Set player side size
        if !pbCanDoubleBattle?
          pbMessage(_INTL("你只有一只宝可梦。"))
          next
        end
        maxVal = (pbCanTripleBattle?) ? 3 : 2
        params = ChooseNumberParams.new
        params.setRange(1, maxVal)
        params.setInitialValue(size0)
        params.setCancelValue(0)
        newSize = pbMessageChooseNumber(
           _INTL("选择己方上场数量（最大 {1}）。", maxVal), params)
        size0 = newSize if newSize > 0
      elsif pkmnCmd == pkmnCmds.length - 3   # Add Pokémon
        species = pbChooseSpeciesList
        if species
          params = ChooseNumberParams.new
          params.setRange(1, GameData::GrowthRate.max_level)
          params.setInitialValue(5)
          params.setCancelValue(0)
          level = pbMessageChooseNumber(_INTL("设置野生 {1} 的等级。",
             GameData::Species.get(species).name), params)
          pkmn.push(Pokemon.new(species, level)) if level > 0
        end
      else                                   # Edit a Pokémon
        if pbConfirmMessage(_INTL("要修改这只宝可梦吗？"))
          scr = PokemonDebugPartyScreen.new
          scr.pbPokemonDebug(pkmn[pkmnCmd], -1, nil, true)
          scr.pbEndScreen
        elsif pbConfirmMessage(_INTL("要删除这只宝可梦吗？"))
          pkmn[pkmnCmd] = nil
          pkmn.compact!
        end
      end
    end
    next false
  }
})

DebugMenuCommands.register("testtrainerbattle", {
  "parent"      => "battlemenu",
  "name"        => _INTL("测试训练家对战"),
  "description" => _INTL("与你选择的训练家进行单场对战。"),
  "effect"      => proc {
    trainerdata = pbListScreen(_INTL("单打训练家"), TrainerBattleLister.new(0, false))
    if trainerdata
      pbTrainerBattle(trainerdata[0], trainerdata[1], nil, false, trainerdata[2], true)
    end
    next false
  }
})

DebugMenuCommands.register("testtrainerbattleadvanced", {
  "parent"      => "battlemenu",
  "name"        => _INTL("测试训练家对战（高级）"),
  "description" => _INTL("与 1 名或多名训练家开战，战斗规模自选。"),
  "effect"      => proc {
    trainers = []
    size0 = 1
    size1 = 1
    trainerCmd = 0
    loop do
      trainerCmds = []
      trainers.each { |t| trainerCmds.push(sprintf("%s x%d", t[1].full_name, t[1].party_count)) }
      trainerCmds.push(_INTL("【添加训练家】"))
      trainerCmds.push(_INTL("【设置我方一侧的尺寸】"))
      trainerCmds.push(_INTL("【设置对方一侧的尺寸】"))
      trainerCmds.push(_INTL("[开始 {1}v{2} 战斗]", size0, size1))
      trainerCmd = pbShowCommands(nil, trainerCmds, -1, trainerCmd)
      break if trainerCmd < 0
      if trainerCmd == trainerCmds.length - 1      # Start battle
        if trainers.length == 0
          pbMessage(_INTL("没有选择训练家，无法开始战斗。"))
          next
        elsif size1 < trainers.length
          pbMessage(_INTL("对方上场数量无效，至少应为 {1}。", trainers.length))
          next
        elsif size1 > trainers.length && trainers[0][1].party_count == 1
          pbMessage(
             _INTL("对方上场数量不能是 {1}：那要求第一位训练家至少拥有 2 只宝可梦，而对方没有。",
             size1))
          next
        end
        setBattleRule(sprintf("%dv%d", size0, size1))
        battleArgs = []
        trainers.each { |t| battleArgs.push(t[1]) }
        pbTrainerBattleCore(*battleArgs)
        break
      elsif trainerCmd == trainerCmds.length - 2   # Set opponent side size
        if trainers.length == 0 || (trainers.length == 1 && trainers[0][1].party_count == 1)
          pbMessage(_INTL("没有选择训练家，或该训练家只有一只宝可梦。"))
          next
        end
        maxVal = 2
        maxVal = 3 if trainers.length >= 3 ||
                      (trainers.length == 2 && trainers[0][1].party_count >= 2) ||
                      trainers[0][1].party_count >= 3
        params = ChooseNumberParams.new
        params.setRange(1, maxVal)
        params.setInitialValue(size1)
        params.setCancelValue(0)
        newSize = pbMessageChooseNumber(
           _INTL("选择对方上场数量（最大 {1}）。", maxVal), params)
        size1 = newSize if newSize > 0
      elsif trainerCmd == trainerCmds.length - 3   # Set player side size
        if !pbCanDoubleBattle?
          pbMessage(_INTL("你只有一只宝可梦。"))
          next
        end
        maxVal = (pbCanTripleBattle?) ? 3 : 2
        params = ChooseNumberParams.new
        params.setRange(1, maxVal)
        params.setInitialValue(size0)
        params.setCancelValue(0)
        newSize = pbMessageChooseNumber(
           _INTL("选择己方上场数量（最大 {1}）。", maxVal), params)
        size0 = newSize if newSize > 0
      elsif trainerCmd == trainerCmds.length - 4   # Add trainer
        trainerdata = pbListScreen(_INTL("选择训练家"), TrainerBattleLister.new(0, false))
        if trainerdata
          tr = pbLoadTrainer(trainerdata[0], trainerdata[1], trainerdata[2])
          trainers.push([0, tr])
        end
      else                                         # Edit a trainer
        if pbConfirmMessage(_INTL("要修改这个训练家吗？"))
          trainerdata = pbListScreen(_INTL("选择训练家"),
             TrainerBattleLister.new(trainers[trainerCmd][0], false))
          if trainerdata
            tr = pbLoadTrainer(trainerdata[0], trainerdata[1], trainerdata[2])
            trainers[trainerCmd] = [0, tr]
          end
        elsif pbConfirmMessage(_INTL("要删除这个训练家吗？"))
          trainers[trainerCmd] = nil
          trainers.compact!
        end
      end
    end
    next false
  }
})

DebugMenuCommands.register("togglelogging", {
  "parent"      => "battlemenu",
  "name"        => _INTL("切换战斗日志"),
  "description" => _INTL("把战斗调试日志记录到 Data/debuglog.txt。"),
  "effect"      => proc {
    $INTERNAL = !$INTERNAL
    pbMessage(_INTL("战斗调试日志会生成在 Data 文件夹里。")) if $INTERNAL
    pbMessage(_INTL("不再生成战斗调试日志。")) if !$INTERNAL
  }
})

DebugMenuCommands.register("resettrainers", {
  "parent"      => "battlemenu",
  "name"        => _INTL("重置地图训练家"),
  "description" => _INTL("把所有名字里带 Trainer 的事件的自开关 A、B 关闭。"),
  "effect"      => proc {
    if $game_map
      for event in $game_map.events.values
        if event.name[/trainer/i]
          $game_self_switches[[$game_map.map_id, event.id, "A"]] = false
          $game_self_switches[[$game_map.map_id, event.id, "B"]] = false
        end
      end
      $game_map.need_refresh = true
      pbMessage(_INTL("本地图所有训练家已重置。"))
    else
      pbMessage(_INTL("这里不能使用这个指令。"))
    end
  }
})

DebugMenuCommands.register("readyrematches", {
  "parent"      => "battlemenu",
  "name"        => _INTL("准备所有手机再战"),
  "description" => _INTL("让手机中所有训练家可再次对战。"),
  "effect"      => proc {
    if !$PokemonGlobal.phoneNumbers || $PokemonGlobal.phoneNumbers.length == 0
      pbMessage(_INTL("电话里没有训练家。"))
    else
      for i in $PokemonGlobal.phoneNumbers
        next if i.length != 8   # Isn't a trainer with an event
        i[4] = 2
        pbSetReadyToBattle(i)
      end
      pbMessage(_INTL("电话里的所有训练家现在都可以再战了。"))
    end
  }
})

DebugMenuCommands.register("roamers", {
  "parent"      => "battlemenu",
  "name"        => _INTL("游走宝可梦"),
  "description" => _INTL("切换并编辑所有游走宝可梦。"),
  "effect"      => proc {
    pbDebugRoamers
  }
})

DebugMenuCommands.register("encounterversion", {
  "parent"      => "battlemenu",
  "name"        => _INTL("设置遭遇版本"),
  "description" => _INTL("选择使用哪个版本的野生遭遇。"),
  "effect"      => proc {
    params = ChooseNumberParams.new
    params.setRange(0, 99)
    params.setInitialValue($PokemonGlobal.encounter_version)
    params.setCancelValue(-1)
    value = pbMessageChooseNumber(_INTL("要把遭遇表版本设为多少？"), params)
    if value >= 0
      $PokemonGlobal.encounter_version = value
    end
  }
})

#===============================================================================
# Item options
#===============================================================================
DebugMenuCommands.register("itemsmenu", {
  "parent"      => "main",
  "name"        => _INTL("道具选项…"),
  "description" => _INTL("给予或收回道具。")
})

DebugMenuCommands.register("additem", {
  "parent"      => "itemsmenu",
  "name"        => _INTL("添加道具"),
  "description" => _INTL("选择一种道具及其数量加入背包。"),
  "effect"      => proc {
    pbListScreenBlock(_INTL("添加道具"), ItemLister.new) { |button, item|
      if button == Input::USE && item
        params = ChooseNumberParams.new
        params.setRange(1, Settings::BAG_MAX_PER_SLOT)
        params.setInitialValue(1)
        params.setCancelValue(0)
        qty = pbMessageChooseNumber(_INTL("要添加多少个 {1}？",
           GameData::Item.get(item).name_plural), params)
        if qty > 0
          $PokemonBag.pbStoreItem(item, qty)
          pbMessage(_INTL("给予了 {1} 个 {2}。", qty, GameData::Item.get(item).name))
        end
      end
    }
  }
})

DebugMenuCommands.register("fillbag", {
  "parent"      => "itemsmenu",
  "name"        => _INTL("装满背包"),
  "description" => _INTL("向背包添加每种道具各若干个。"),
  "effect"      => proc {
    params = ChooseNumberParams.new
    params.setRange(1, Settings::BAG_MAX_PER_SLOT)
    params.setInitialValue(1)
    params.setCancelValue(0)
    qty = pbMessageChooseNumber(_INTL("选择道具数量。"), params)
    if qty > 0
      GameData::Item.each { |i| $PokemonBag.pbStoreItem(i.id, qty) }
      pbMessage(_INTL("背包里每种道具都装入了 {1} 个。", qty))
    end
  }
})

DebugMenuCommands.register("emptybag", {
  "parent"      => "itemsmenu",
  "name"        => _INTL("清空背包"),
  "description" => _INTL("移除背包中所有道具。"),
  "effect"      => proc {
    $PokemonBag.clear
    pbMessage(_INTL("背包已清空。"))
  }
})

#===============================================================================
# Pokémon options
#===============================================================================
DebugMenuCommands.register("pokemonmenu", {
  "parent"      => "main",
  "name"        => _INTL("宝可梦选项…"),
  "description" => _INTL("给予宝可梦、恢复队伍、填满/清空电脑寄存等。")
})

DebugMenuCommands.register("addpokemon", {
  "parent"      => "pokemonmenu",
  "name"        => _INTL("添加宝可梦"),
  "description" => _INTL("给自己一只指定种类/等级的宝可梦。队伍满时送入电脑。"),
  "effect"      => proc {
    species = pbChooseSpeciesList
    if species
      params = ChooseNumberParams.new
      params.setRange(1, GameData::GrowthRate.max_level)
      params.setInitialValue(5)
      params.setCancelValue(0)
      level = pbMessageChooseNumber(_INTL("设置该宝可梦的等级。"), params)
      pbAddPokemon(species, level) if level > 0
    end
  }
})

DebugMenuCommands.register("demoparty", {
  "parent"      => "pokemonmenu",
  "name"        => _INTL("给予演示队伍"),
  "description" => _INTL("给自己 6 只预设宝可梦，会覆盖当前队伍。"),
  "effect"      => proc {
    party = []
    species = [:PIKACHU, :PIDGEOTTO, :KADABRA, :GYARADOS, :DIGLETT, :CHANSEY]
    for id in species
      party.push(id) if GameData::Species.exists?(id)
    end
    $Trainer.party.clear
    # Generate Pokémon of each species at level 20
    party.each do |species|
      pkmn = Pokemon.new(species, 20)
      $Trainer.party.push(pkmn)
      $Trainer.pokedex.register(pkmn)
      $Trainer.pokedex.set_owned(species)
      case species
      when :PIDGEOTTO
        pkmn.learn_move(:FLY)
      when :KADABRA
        pkmn.learn_move(:FLASH)
        pkmn.learn_move(:TELEPORT)
      when :GYARADOS
        pkmn.learn_move(:SURF)
        pkmn.learn_move(:DIVE)
        pkmn.learn_move(:WATERFALL)
      when :DIGLETT
        pkmn.learn_move(:DIG)
        pkmn.learn_move(:CUT)
        pkmn.learn_move(:HEADBUTT)
        pkmn.learn_move(:ROCKSMASH)
      when :CHANSEY
        pkmn.learn_move(:SOFTBOILED)
        pkmn.learn_move(:STRENGTH)
        pkmn.learn_move(:SWEETSCENT)
      end
      pkmn.record_first_moves
    end
    pbMessage(_INTL("已用演示宝可梦填满队伍。"))
  }
})

DebugMenuCommands.register("healparty", {
  "parent"      => "pokemonmenu",
  "name"        => _INTL("恢复全队"),
  "description" => _INTL("完全恢复队伍中所有宝可梦的 HP/状态/PP。"),
  "effect"      => proc {
    $Trainer.party.each { |pkmn| pkmn.heal }
    pbMessage(_INTL("你的宝可梦已完全回复。"))
  }
})

DebugMenuCommands.register("quickhatch", {
  "parent"      => "pokemonmenu",
  "name"        => _INTL("快速孵化"),
  "description" => _INTL("让队伍中所有蛋只需再走一步即可孵化。"),
  "effect"      => proc {
    $Trainer.party.each { |pkmn| pkmn.steps_to_hatch = 1 if pkmn.egg? }
    pbMessage(_INTL("队伍里的所有蛋现在只需 1 步就能孵化。"))
  }
})

DebugMenuCommands.register("fillboxes", {
  "parent"      => "pokemonmenu",
  "name"        => _INTL("填满寄存箱"),
  "description" => _INTL("向寄存系统添加每种宝可梦各一只（50 级）。"),
  "effect"      => proc {
    added = 0
    box_qty = $PokemonStorage.maxPokemon(0)
    completed = true
    GameData::Species.each do |species_data|
      sp = species_data.species
      f = species_data.form
      # Record each form of each species as seen and owned
      if f == 0
        if [:AlwaysMale, :AlwaysFemale, :Genderless].include?(species_data.gender_ratio)
          g = (species_data.gender_ratio == :AlwaysFemale) ? 1 : 0
          $Trainer.pokedex.register(sp, g, f, false)
        else   # Both male and female
          $Trainer.pokedex.register(sp, 0, f, false)
          $Trainer.pokedex.register(sp, 1, f, false)
        end
        $Trainer.pokedex.set_owned(sp, false)
      elsif species_data.real_form_name && !species_data.real_form_name.empty?
        g = (species_data.gender_ratio == :AlwaysFemale) ? 1 : 0
        $Trainer.pokedex.register(sp, g, f, false)
      end
      # Add Pokémon (if form 0, i.e. one of each species)
      next if f != 0
      if added >= Settings::NUM_STORAGE_BOXES * box_qty
        completed = false
        next
      end
      added += 1
      $PokemonStorage[(added - 1) / box_qty, (added - 1) % box_qty] = Pokemon.new(sp, 50)
    end
    $Trainer.pokedex.refresh_accessible_dexes
    pbMessage(_INTL("仓库已用每种各 1 只宝可梦填满。"))
    if !completed
      pbMessage(_INTL("注意：寄存空间（{1} 个 {2} 格仓库）少于宝可梦种类数。",
         Settings::NUM_STORAGE_BOXES, box_qty))
    end
  }
})

DebugMenuCommands.register("clearboxes", {
  "parent"      => "pokemonmenu",
  "name"        => _INTL("清空寄存箱"),
  "description" => _INTL("移除寄存系统中所有宝可梦。"),
  "effect"      => proc {
    for i in 0...$PokemonStorage.maxBoxes
      for j in 0...$PokemonStorage.maxPokemon(i)
        $PokemonStorage[i, j] = nil
      end
    end
    pbMessage(_INTL("仓库已清空。"))
  }
})

DebugMenuCommands.register("openstorage", {
  "parent"      => "pokemonmenu",
  "name"        => _INTL("访问宝可梦寄存系统"),
  "description" => _INTL("以整理箱子模式打开宝可梦寄存箱。"),
  "effect"      => proc {
    pbFadeOutIn {
      scene = PokemonStorageScene.new
      screen = PokemonStorageScreen.new(scene, $PokemonStorage)
      screen.pbStartScreen(0)
    }
  }
})

#===============================================================================
# Player options
#===============================================================================
DebugMenuCommands.register("playermenu", {
  "parent"      => "main",
  "name"        => _INTL("玩家选项…"),
  "description" => _INTL("设置金钱、徽章、图鉴、玩家外观与姓名等。")
})

DebugMenuCommands.register("setbadges", {
  "parent"      => "playermenu",
  "name"        => _INTL("设置徽章"),
  "description" => _INTL("切换各道馆徽章的持有情况。"),
  "effect"      => proc {
    badgecmd = 0
    loop do
      badgecmds = []
      badgecmds.push(_INTL("全部给予"))
      badgecmds.push(_INTL("全部移除"))
      for i in 0...24
        badgecmds.push(_INTL("{1} 徽章 {2}", $Trainer.badges[i] ? "[Y]" : "[  ]", i + 1))
      end
      badgecmd = pbShowCommands(nil, badgecmds, -1, badgecmd)
      break if badgecmd < 0
      if badgecmd == 0   # Give all
        24.times { |i| $Trainer.badges[i] = true }
      elsif badgecmd == 1   # Remove all
        24.times { |i| $Trainer.badges[i] = false }
      else
        $Trainer.badges[badgecmd - 2] = !$Trainer.badges[badgecmd - 2]
      end
    end
  }
})

DebugMenuCommands.register("setmoney", {
  "parent"      => "playermenu",
  "name"        => _INTL("设置金钱"),
  "description" => _INTL("编辑你拥有的金钱数。"),
  "effect"      => proc {
    params = ChooseNumberParams.new
    params.setRange(0, Settings::MAX_MONEY)
    params.setDefaultValue($Trainer.money)
    $Trainer.money = pbMessageChooseNumber(_INTL("设置玩家的金钱。"), params)
    pbMessage(_INTL("你现在有 ${1}。", $Trainer.money.to_s_formatted))
  }
})

DebugMenuCommands.register("setcoins", {
  "parent"      => "playermenu",
  "name"        => _INTL("设置代币"),
  "description" => _INTL("编辑你拥有的游戏中心代币数。"),
  "effect"      => proc {
    params = ChooseNumberParams.new
    params.setRange(0, Settings::MAX_COINS)
    params.setDefaultValue($Trainer.coins)
    $Trainer.coins = pbMessageChooseNumber(_INTL("设置玩家的金币数量。"), params)
    pbMessage(_INTL("你现在有 {1} 代币。", $Trainer.coins.to_s_formatted))
  }
})

DebugMenuCommands.register("setbp", {
  "parent"      => "playermenu",
  "name"        => _INTL("设置对战点数"),
  "description" => _INTL("编辑你拥有的对战点数。"),
  "effect"      => proc {
    params = ChooseNumberParams.new
    params.setRange(0, Settings::MAX_BATTLE_POINTS)
    params.setDefaultValue($Trainer.battle_points)
    $Trainer.battle_points = pbMessageChooseNumber(_INTL("设置玩家的 BP 数量。"), params)
    pbMessage(_INTL("你现在有 {1} BP。", $Trainer.battle_points.to_s_formatted))
  }
})

DebugMenuCommands.register("toggleshoes", {
  "parent"      => "playermenu",
  "name"        => _INTL("切换跑鞋"),
  "description" => _INTL("切换跑鞋的持有情况。"),
  "effect"      => proc {
    $Trainer.has_running_shoes = !$Trainer.has_running_shoes
    pbMessage(_INTL("已给予跑步鞋。")) if $Trainer.has_running_shoes
    pbMessage(_INTL("已失去跑步鞋。")) if !$Trainer.has_running_shoes
  }
})

DebugMenuCommands.register("togglepokegear", {
  "parent"      => "playermenu",
  "name"        => _INTL("切换宝可装置"),
  "description" => _INTL("切换宝可装置的持有情况。"),
  "effect"      => proc {
    $Trainer.has_pokegear = !$Trainer.has_pokegear
    pbMessage(_INTL("已给予宝可钟。")) if $Trainer.has_pokegear
    pbMessage(_INTL("已失去宝可钟。")) if !$Trainer.has_pokegear
  }
})

DebugMenuCommands.register("dexlists", {
  "parent"      => "playermenu",
  "name"        => _INTL("切换宝可梦图鉴与子图鉴"),
  "description" => _INTL("切换宝可梦图鉴持有情况，并编辑地区图鉴可访问性。"),
  "effect"      => proc {
    dexescmd = 0
    loop do
      dexescmds = []
      dexescmds.push(_INTL("拥有图鉴：{1}", $Trainer.has_pokedex ? "[YES]" : "[NO]"))
      dex_names = Settings.pokedex_names
      for i in 0...dex_names.length
        name = (dex_names[i].is_a?(Array)) ? dex_names[i][0] : dex_names[i]
        unlocked = $Trainer.pokedex.unlocked?(i)
        dexescmds.push(_INTL("{1} {2}", unlocked ? "[Y]" : "[  ]", name))
      end
      dexescmd = pbShowCommands(nil, dexescmds, -1, dexescmd)
      break if dexescmd < 0
      dexindex = dexescmd - 1
      if dexindex < 0   # Toggle Pokédex ownership
        $Trainer.has_pokedex = !$Trainer.has_pokedex
      else   # Toggle Regional Dex accessibility
        if $Trainer.pokedex.unlocked?(dexindex)
          $Trainer.pokedex.lock(dexindex)
        else
          $Trainer.pokedex.unlock(dexindex)
        end
      end
    end
  }
})

DebugMenuCommands.register("setplayer", {
  "parent"      => "playermenu",
  "name"        => _INTL("设置玩家角色"),
  "description" => _INTL("编辑 metadata.txt 里定义的主角形象。"),
  "effect"      => proc {
    limit = 0
    for i in 0...8
      meta = GameData::Metadata.get_player(i)
      next if meta
      limit = i
      break
    end
    if limit <= 1
      pbMessage(_INTL("只定义了一个主角。"))
    else
      params = ChooseNumberParams.new
      params.setRange(0, limit - 1)
      params.setDefaultValue($Trainer.character_ID)
      newid = pbMessageChooseNumber(_INTL("选择新的主角形象。"), params)
      if newid != $Trainer.character_ID
        pbChangePlayer(newid)
        pbMessage(_INTL("主角形象已更换。"))
      end
    end
  }
})

DebugMenuCommands.register("changeoutfit", {
  "parent"      => "playermenu",
  "name"        => _INTL("设置玩家服装"),
  "description" => _INTL("编辑玩家服装编号。"),
  "effect"      => proc {
    oldoutfit = $Trainer.outfit
    params = ChooseNumberParams.new
    params.setRange(0, 99)
    params.setDefaultValue(oldoutfit)
    $Trainer.outfit = pbMessageChooseNumber(_INTL("设置主角装扮。"), params)
    pbMessage(_INTL("主角装扮已更换。")) if $Trainer.outfit != oldoutfit
  }
})

DebugMenuCommands.register("renameplayer", {
  "parent"      => "playermenu",
  "name"        => _INTL("设置玩家姓名"),
  "description" => _INTL("重命名玩家。"),
  "effect"      => proc {
    trname = pbEnterPlayerName("Your name?", 0, Settings::MAX_PLAYER_NAME_SIZE, $Trainer.name)
    if nil_or_empty?(trname) && pbConfirmMessage(_INTL("给自己取个默认名字吗？"))
      trainertype = $Trainer.trainer_type
      gender      = pbGetTrainerTypeGender(trainertype)
      trname      = pbSuggestTrainerName(gender)
    end
    if nil_or_empty?(trname)
      pbMessage(_INTL("玩家的名字仍为 {1}。", $Trainer.name))
    else
      $Trainer.name = trname
      pbMessage(_INTL("玩家的名字已改为 {1}。", $Trainer.name))
    end
  }
})

DebugMenuCommands.register("randomid", {
  "parent"      => "playermenu",
  "name"        => _INTL("随机化玩家 ID"),
  "description" => _INTL("为玩家生成一个随机新 ID。"),
  "effect"      => proc {
    $Trainer.id = rand(2 ** 16) | rand(2 ** 16) << 16
    pbMessage(_INTL("玩家的 ID 已改为 {1}（完整 ID：{2}）。", $Trainer.public_ID, $Trainer.id))
  }
})

#===============================================================================
# Information editors
#===============================================================================
DebugMenuCommands.register("editorsmenu", {
  "parent"      => "main",
  "name"        => _INTL("信息编辑器…"),
  "description" => _INTL("编辑 PBS 文件中的信息、地形标签、战斗动画等。"),
  "always_show" => true
})

DebugMenuCommands.register("setmetadata", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑元数据"),
  "description" => _INTL("编辑全局与地图元数据。"),
  "always_show" => true,
  "effect"      => proc {
    pbMetadataScreen(pbDefaultMap)
  }
})

DebugMenuCommands.register("mapconnections", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑地图连接"),
  "description" => _INTL("用可视化界面连接地图，也可编辑地图遭遇/元数据。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbConnectionsEditor }
  }
})

DebugMenuCommands.register("terraintags", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑地形标签"),
  "description" => _INTL("编辑图块集内图块的地形标签。8 号及以上的标签需要此项。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbTilesetScreen }
  }
})

DebugMenuCommands.register("setencounters", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑野生遭遇"),
  "description" => _INTL("编辑各地图可遇到的野生宝可梦及遭遇方式。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbEncountersEditor }
  }
})

DebugMenuCommands.register("trainertypes", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑训练家类型"),
  "description" => _INTL("编辑训练家类型的属性。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbTrainerTypeEditor }
  }
})

DebugMenuCommands.register("edittrainers", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑单个训练家"),
  "description" => _INTL("编辑单个训练家及其宝可梦和道具。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbTrainerBattleEditor }
  }
})

DebugMenuCommands.register("edititems", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑道具"),
  "description" => _INTL("编辑道具数据。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbItemEditor }
  }
})

DebugMenuCommands.register("editpokemon", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑宝可梦"),
  "description" => _INTL("编辑宝可梦种类数据。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbPokemonEditor }
  }
})

DebugMenuCommands.register("editdexes", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑地区图鉴"),
  "description" => _INTL("创建、重排和删除地区图鉴列表。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbRegionalDexEditorMain }
  }
})

DebugMenuCommands.register("positionsprites", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("编辑宝可梦精灵位置"),
  "description" => _INTL("重新排列战斗中的宝可梦精灵。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn {
      sp = SpritePositioner.new
      sps = SpritePositionerScreen.new(sp)
      sps.pbStart
    }
  }
})

DebugMenuCommands.register("autopositionsprites", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("自动排列所有精灵"),
  "description" => _INTL("自动重新排列战斗中所有宝可梦精灵。请谨慎使用。"),
  "always_show" => true,
  "effect"      => proc {
    if pbConfirmMessage(_INTL("确定要重新排列所有图块吗？"))
      msgwindow = pbCreateMessageWindow
      pbMessageDisplay(msgwindow, _INTL("正在重新排列所有图块，请稍候。"), false)
      Graphics.update
      pbAutoPositionAll
      pbDisposeMessageWindow(msgwindow)
    end
  }
})

DebugMenuCommands.register("animeditor", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("战斗动画编辑器"),
  "description" => _INTL("编辑战斗动画。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbAnimationEditor }
  }
})

DebugMenuCommands.register("animorganiser", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("战斗动画管理器"),
  "description" => _INTL("重排/添加/删除战斗动画。"),
  "always_show" => true,
  "effect"      => proc {
    pbFadeOutIn { pbAnimationsOrganiser }
  }
})

DebugMenuCommands.register("importanims", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("导入所有战斗动画"),
  "description" => _INTL("从 Animations 文件夹导入所有战斗动画。"),
  "always_show" => true,
  "effect"      => proc {
    pbImportAllAnimations
  }
})

DebugMenuCommands.register("exportanims", {
  "parent"      => "editorsmenu",
  "name"        => _INTL("导出所有战斗动画"),
  "description" => _INTL("把所有战斗动画分别导出到 Animations 文件夹。"),
  "always_show" => true,
  "effect"      => proc {
    pbExportAllAnimations
  }
})

#===============================================================================
# Other options
#===============================================================================
DebugMenuCommands.register("othermenu", {
  "parent"      => "main",
  "name"        => _INTL("其他选项…"),
  "description" => _INTL("神秘礼物、翻译、编译数据等。"),
  "always_show" => true
})

DebugMenuCommands.register("mysterygift", {
  "parent"      => "othermenu",
  "name"        => _INTL("管理神秘礼物"),
  "description" => _INTL("编辑并启用/停用神秘礼物。"),
  "always_show" => true,
  "effect"      => proc {
    pbManageMysteryGifts
  }
})

DebugMenuCommands.register("extracttext", {
  "parent"      => "othermenu",
  "name"        => _INTL("提取文本"),
  "description" => _INTL("把游戏内所有文本提取到单个文件以便翻译。"),
  "always_show" => true,
  "effect"      => proc {
    pbExtractText
  }
})

DebugMenuCommands.register("compiletext", {
  "parent"      => "othermenu",
  "name"        => _INTL("编译文本"),
  "description" => _INTL("导入文本并转换为语言文件。"),
  "always_show" => true,
  "effect"      => proc {
    pbCompileTextUI
  }
})

DebugMenuCommands.register("compiledata", {
  "parent"      => "othermenu",
  "name"        => _INTL("编译数据"),
  "description" => _INTL("完全编译所有数据。"),
  "always_show" => true,
  "effect"      => proc {
    msgwindow = pbCreateMessageWindow
    Compiler.compile_all(true) { |msg| pbMessageDisplay(msgwindow, msg, false); echoln(msg) }
    pbMessageDisplay(msgwindow, _INTL("全部游戏数据已编译。"))
    pbDisposeMessageWindow(msgwindow)
  }
})

DebugMenuCommands.register("createpbs", {
  "parent"      => "othermenu",
  "name"        => _INTL("创建 PBS 文件"),
  "description" => _INTL("选择单个或全部 PBS 文件并生成。"),
  "always_show" => true,
  "effect"      => proc {
    cmd = 0
    cmds = [
      _INTL("【全部创建】"),
      "abilities.txt",
      "berryplants.txt",
      "connections.txt",
      "encounters.txt",
      "items.txt",
      "metadata.txt",
      "moves.txt",
      "phone.txt",
      "pokemon.txt",
      "pokemonforms.txt",
      "regionaldexes.txt",
      "ribbons.txt",
      "shadowmoves.txt",
      "townmap.txt",
      "trainerlists.txt",
      "trainers.txt",
      "trainertypes.txt",
      "types.txt"
    ]
    loop do
      cmd = pbShowCommands(nil, cmds, -1, cmd)
      case cmd
      when 0  then Compiler.write_all
      when 1  then Compiler.write_abilities
      when 2  then Compiler.write_berry_plants
      when 3  then Compiler.write_connections
      when 4  then Compiler.write_encounters
      when 5  then Compiler.write_items
      when 6  then Compiler.write_metadata
      when 7  then Compiler.write_moves
      when 8  then Compiler.write_phone
      when 9  then Compiler.write_pokemon
      when 10 then Compiler.write_pokemon_forms
      when 11 then Compiler.write_regional_dexes
      when 12 then Compiler.write_ribbons
      when 13 then Compiler.write_shadow_movesets
      when 14 then Compiler.write_town_map
      when 15 then Compiler.write_trainer_lists
      when 16 then Compiler.write_trainers
      when 17 then Compiler.write_trainer_types
      when 18 then Compiler.write_types
      else break
      end
      pbMessage(_INTL("文件已写入。"))
    end
  }
})

DebugMenuCommands.register("renamesprites", {
  "parent"      => "othermenu",
  "name"        => _INTL("重命名旧精灵"),
  "description" => _INTL("把宝可梦/道具/训练家精灵从旧位置重命名并移动。"),
  "always_show" => true,
  "effect"      => proc {
    SpriteRenamer.convert_files
  }
})

DebugMenuCommands.register("invalidtiles", {
  "parent"      => "othermenu",
  "name"        => _INTL("修复无效图块"),
  "description" => _INTL("扫描所有地图并清除不存在的图块。"),
  "always_show" => true,
  "effect"      => proc {
    pbDebugFixInvalidTiles
  }
})
