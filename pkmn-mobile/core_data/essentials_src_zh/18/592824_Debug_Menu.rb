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
    commands.add("main","fieldmenu",_INTL("场地选项…"),
       _INTL("传送至地图、编辑开关/变量、使用电脑、编辑培育屋等。"))
    commands.add("fieldmenu","warp",_INTL("传送至地图"),
       _INTL("立即传送到你选择的另一张地图。"))
    # - Optional coordinates
    commands.add("fieldmenu","refreshmap",_INTL("刷新地图"),
       _INTL("让本图所有事件及公共事件自行刷新。"))
    commands.add("fieldmenu","switches",_INTL("开关"),
       _INTL("编辑所有游戏开关（脚本开关除外）。"))
    commands.add("fieldmenu","variables",_INTL("变量"),
       _INTL("编辑所有游戏变量，可设为数字或文本。"))
    commands.add("fieldmenu","usepc",_INTL("使用电脑"),
       _INTL("使用电脑访问宝可梦寄存系统与玩家电脑。"))
    commands.add("fieldmenu","togglewallpapers",_INTL("切换寄存壁纸"),
       _INTL("解锁/锁定宝可梦寄存系统使用的特殊壁纸。"))
    commands.add("fieldmenu","daycare",_INTL("培育屋"),
       _INTL("查看并编辑培育屋中的宝可梦。"))
    commands.add("fieldmenu","relicstone",_INTL("使用古代石"),
       _INTL("暗影宝可梦。选择一只带到古代石进行净化。"))
    commands.add("fieldmenu","purifychamber",_INTL("使用净化室"),
       _INTL("暗影宝可梦。打开净化室进行净化。"))

    commands.add("main","battlemenu",_INTL("战斗选项…"),
       _INTL("开始对战、重置本图训练家、准备再战、编辑游走宝可梦等。"))
    commands.add("battlemenu","testwildbattle",_INTL("测试野生对战"),
       _INTL("与一只野生宝可梦进行单场对战，种类/等级自选。"))
    commands.add("battlemenu","testwildbattleadvanced",_INTL("测试野生对战（高级）"),
       _INTL("与 1 只或多只野生宝可梦开战，战斗规模自选。"))
    commands.add("battlemenu","testtrainerbattle",_INTL("测试训练家对战"),
       _INTL("与你选择的训练家进行单场对战。"))
    commands.add("battlemenu","testtrainerbattleadvanced",_INTL("测试训练家对战（高级）"),
       _INTL("与 1 名或多名训练家开战，战斗规模自选。"))
    commands.add("battlemenu","togglelogging",_INTL("切换战斗日志"),
       _INTL("把战斗调试日志记录到 Data/debuglog.txt。"))
    commands.add("battlemenu","resettrainers",_INTL("重置地图训练家"),
       _INTL("把所有名字里带 Trainer 的事件的自开关 A、B 关闭。"))
    commands.add("battlemenu","readyrematches",_INTL("准备所有手机再战"),
       _INTL("让手机中所有训练家可再次对战。"))
    commands.add("battlemenu","roamers",_INTL("游走宝可梦"),
       _INTL("切换并编辑所有游走宝可梦。"))

    commands.add("main","itemsmenu",_INTL("道具选项…"),
       _INTL("给予或收回道具。"))
    commands.add("itemsmenu","additem",_INTL("添加道具"),
       _INTL("选择一种道具及其数量加入背包。"))
    commands.add("itemsmenu","fillbag",_INTL("装满背包"),
       _INTL("向背包添加每种道具各若干个。"))
    commands.add("itemsmenu","emptybag",_INTL("清空背包"),
       _INTL("移除背包中所有道具。"))

    commands.add("main","pokemonmenu",_INTL("宝可梦选项…"),
       _INTL("给予宝可梦、恢复队伍、填满/清空电脑寄存等。"))
    commands.add("pokemonmenu","addpokemon",_INTL("添加宝可梦"),
       _INTL("给自己一只指定种类/等级的宝可梦。队伍满时送入电脑。"))
    commands.add("pokemonmenu","demoparty",_INTL("给予演示队伍"),
       _INTL("给自己 6 只预设宝可梦，会覆盖当前队伍。"))
    commands.add("pokemonmenu","healparty",_INTL("恢复全队"),
       _INTL("完全恢复队伍中所有宝可梦的 HP/状态/PP。"))
    commands.add("pokemonmenu","quickhatch",_INTL("快速孵化"),
       _INTL("让队伍中所有蛋只需再走一步即可孵化。"))
    commands.add("pokemonmenu","fillboxes",_INTL("填满寄存箱"),
       _INTL("向寄存系统添加每种宝可梦各一只（50 级）。"))
    commands.add("pokemonmenu","clearboxes",_INTL("清空寄存箱"),
       _INTL("移除寄存系统中所有宝可梦。"))
    commands.add("pokemonmenu","openstorage",_INTL("访问宝可梦寄存系统"),
       _INTL("以整理箱子模式打开宝可梦寄存箱。"))

    commands.add("main","playermenu",_INTL("玩家选项…"),
       _INTL("设置金钱、徽章、图鉴、玩家外观与姓名等。"))
    commands.add("playermenu","setbadges",_INTL("设置徽章"),
       _INTL("切换各道馆徽章的持有情况。"))
    commands.add("playermenu","setmoney",_INTL("设置金钱"),
       _INTL("编辑你拥有的金钱数。"))
    commands.add("playermenu","setcoins",_INTL("设置代币"),
       _INTL("编辑你拥有的游戏中心代币数。"))
    commands.add("playermenu","toggleshoes",_INTL("切换跑鞋"),
       _INTL("切换跑鞋的持有情况。"))
    commands.add("playermenu","togglepokegear",_INTL("切换宝可装置"),
       _INTL("切换宝可装置的持有情况。"))
    commands.add("playermenu","dexlists",_INTL("切换宝可梦图鉴与子图鉴"),
       _INTL("切换宝可梦图鉴持有情况，并编辑地区图鉴可访问性。"))
    commands.add("playermenu","setplayer",_INTL("设置玩家角色"),
       _INTL("编辑 metadata.txt 里定义的主角形象。"))
    commands.add("playermenu","changeoutfit",_INTL("设置玩家服装"),
       _INTL("编辑玩家服装编号。"))
    commands.add("playermenu","renameplayer",_INTL("设置玩家姓名"),
       _INTL("重命名玩家。"))
    commands.add("playermenu","randomid",_INTL("随机玩家ID"),
       _INTL("为玩家生成一个随机新 ID。"))
  end

  commands.add("main","editorsmenu",_INTL("信息编辑器…"),
     _INTL("编辑 PBS 文件中的信息、地形标签、战斗动画等。"))
  commands.add("editorsmenu","setmetadata",_INTL("编辑元数据"),
     _INTL("编辑全局以及地图专属的 metadata。"))
  commands.add("editorsmenu","mapconnections",_INTL("编辑地图连接"),
     _INTL("用可视化界面连接地图，也可编辑地图遭遇/元数据。"))
  commands.add("editorsmenu","terraintags",_INTL("编辑地形标签"),
     _INTL("编辑图块集内图块的地形标签。8 号及以上的标签需要此项。"))
  commands.add("editorsmenu","setencounters",_INTL("编辑野生遭遇"),
     _INTL("编辑各地图可遇到的野生宝可梦及遭遇方式。"))
  commands.add("editorsmenu","trainertypes",_INTL("编辑训练家类型"),
     _INTL("编辑训练家类型的属性。"))
  commands.add("editorsmenu","edittrainers",_INTL("编辑单个训练家"),
     _INTL("编辑单个训练家及其宝可梦和道具。"))
  commands.add("editorsmenu","edititems",_INTL("编辑道具"),
     _INTL("编辑道具数据。"))
  commands.add("editorsmenu","editpokemon",_INTL("编辑宝可梦"),
     _INTL("编辑宝可梦种类数据。"))
  commands.add("editorsmenu","editdexes",_INTL("编辑地区图鉴"),
     _INTL("创建、重排和删除地区图鉴列表。"))
  commands.add("editorsmenu","positionsprites",_INTL("编辑宝可梦精灵位置"),
     _INTL("重新排列战斗中的宝可梦精灵。"))
  commands.add("editorsmenu","autopositionsprites",_INTL("自动排列所有精灵"),
     _INTL("自动重新排列战斗中所有宝可梦精灵。请谨慎使用。"))
  commands.add("editorsmenu","animeditor",_INTL("战斗动画编辑器"),
     _INTL("编辑战斗动画。"))
  commands.add("editorsmenu","animorganiser",_INTL("战斗动画管理器"),
     _INTL("重排/添加/删除战斗动画。"))
  commands.add("editorsmenu","importanims",_INTL("导入所有战斗动画"),
     _INTL("从 Animations 文件夹导入所有战斗动画。"))
  commands.add("editorsmenu","exportanims",_INTL("导出所有战斗动画"),
     _INTL("把所有战斗动画分别导出到 Animations 文件夹。"))

  commands.add("main","othermenu",_INTL("其他选项…"),
     _INTL("神秘礼物、翻译、编译数据等。"))
  commands.add("othermenu","mysterygift",_INTL("管理神秘礼物"),
    _INTL("编辑并启用/停用神秘礼物。"))
  commands.add("othermenu","extracttext",_INTL("提取文本"),
    _INTL("把游戏内所有文本提取到单个文件以便翻译。"))
  commands.add("othermenu","compiletext",_INTL("编译文本"),
    _INTL("导入文本并转换为语言文件。"))
  commands.add("othermenu","compiledata",_INTL("编译数据"),
    _INTL("完全编译所有数据。"))
  commands.add("othermenu","debugconsole",_INTL("调试控制台"),
    _INTL("打开调试控制台。"))

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
      pbDisposeMessageWindow(sprites["textbox"])
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
        pbCancelVehicles
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
    pbMessage(_INTL("地图将刷新。"))
  when "switches"
    pbDebugVariables(0)
  when "variables"
    pbDebugVariables(1)
  when "usepc"
    pbPokeCenterPC
  when "togglewallpapers"
    w = $PokemonStorage.allWallpapers
    if w.length<=PokemonStorage::BASICWALLPAPERQTY
      pbMessage(_INTL("没有定义特殊壁纸。"))
    else
      paperscmd = 0
      unlockarray = $PokemonStorage.unlockedWallpapers
      loop do
        paperscmds = []
        paperscmds.push(_INTL("全部解锁"))
        paperscmds.push(_INTL("全部锁定"))
        for i in PokemonStorage::BASICWALLPAPERQTY...w.length
          paperscmds.push(_INTL("{1} {2}",unlockarray[i] ? "[Y]" : "[  ]",w[i]))
        end
        paperscmd = pbShowCommands(nil,paperscmds,-1,paperscmd)
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
      params.setRange(1,PBExperience.maxLevel)
      params.setInitialValue(5)
      params.setCancelValue(0)
      level = pbMessageChooseNumber(_INTL("设置野生 {1} 的等级。",PBSpecies.getName(species)),params)
      if level>0
        $PokemonTemp.encounterType = -1
        pbWildBattle(species,level)
      end
    end
  when "testwildbattleadvanced"
    pkmn = []
    size0 = 1
    pkmnCmd = 0
    loop do
      pkmnCmds = []
      pkmn.each do |p|
        pkmnCmds.push(sprintf("%s Lv.%d",p.name,p.level))
      end
      pkmnCmds.push(_INTL("【添加宝可梦】"))
      pkmnCmds.push(_INTL("【设置我方一侧的尺寸】"))
      pkmnCmds.push(_INTL("[开始 {1}v{2} 战斗]",size0,pkmn.length))
      pkmnCmd = pbShowCommands(nil,pkmnCmds,-1,pkmnCmd)
      break if pkmnCmd<0
      if pkmnCmd==pkmnCmds.length-1      # Start battle
        if pkmn.length==0
          pbMessage(_INTL("没有选择宝可梦，无法开始战斗。"))
          next
        end
        setBattleRule(sprintf("%dv%d",size0,pkmn.length))
        $PokemonTemp.encounterType = -1
        pbWildBattleCore(*pkmn)
        break
      elsif pkmnCmd==pkmnCmds.length-2   # Set player side size
        if !pbCanDoubleBattle?
          pbMessage(_INTL("你只有一只宝可梦。"))
          next
        end
        maxVal = (pbCanTripleBattle?) ? 3 : 2
        params = ChooseNumberParams.new
        params.setRange(1,maxVal)
        params.setInitialValue(size0)
        params.setCancelValue(0)
        newSize = pbMessageChooseNumber(
           _INTL("选择己方上场数量（最大 {1}）。",maxVal),params)
        size0 = newSize if newSize>0
      elsif pkmnCmd==pkmnCmds.length-3   # Add Pokémon
        species = pbChooseSpeciesList
        if species!=0
          params = ChooseNumberParams.new
          params.setRange(1,PBExperience.maxLevel)
          params.setInitialValue(5)
          params.setCancelValue(0)
          level = pbMessageChooseNumber(_INTL("设置野生 {1} 的等级。",PBSpecies.getName(species)),params)
          if level>0
            pkmn.push(pbNewPkmn(species,level))
          end
        end
      else                                     # Edit a Pokémon
        if pbConfirmMessage(_INTL("要修改这只宝可梦吗？"))
          scr = PokemonDebugPartyScreen.new
          scr.pbPokemonDebug(pkmn[pkmnCmd],-1,nil,true)
          scr.pbEndScreen
        elsif pbConfirmMessage(_INTL("要删除这只宝可梦吗？"))
          pkmn[pkmnCmd] = nil
          pkmn.compact!
        end
      end
    end
  when "testtrainerbattle"
    battle = pbListScreen(_INTL("单打训练家"),TrainerBattleLister.new(0,false))
    if battle
      trainerdata = battle[1]
      pbTrainerBattle(trainerdata[0],trainerdata[1],"...",false,trainerdata[4],true)
    end
  when "testtrainerbattleadvanced"
    trainers = []
    size0 = 1
    size1 = 1
    trainerCmd = 0
    loop do
      trainerCmds = []
      trainers.each do |t|
        trainerCmds.push(sprintf("%s x%d",t[1][0].fullname,t[1][2].length))
      end
      trainerCmds.push(_INTL("【添加训练家】"))
      trainerCmds.push(_INTL("【设置我方一侧的尺寸】"))
      trainerCmds.push(_INTL("【设置对方一侧的尺寸】"))
      trainerCmds.push(_INTL("[开始 {1}v{2} 战斗]",size0,size1))
      trainerCmd = pbShowCommands(nil,trainerCmds,-1,trainerCmd)
      break if trainerCmd<0
      if trainerCmd==trainerCmds.length-1      # Start battle
        if trainers.length==0
          pbMessage(_INTL("没有选择训练家，无法开始战斗。"))
          next
        elsif size1<trainers.length
          pbMessage(_INTL("对方上场数量无效，至少应为 {1}。",trainers.length))
          next
        elsif size1>trainers.length && trainers[0][1][2].length==1
          pbMessage(
             _INTL("对方上场数量不能是 {1}：那要求第一位训练家至少拥有 2 只宝可梦，而对方没有。",
             size1))
          next
        end
        setBattleRule(sprintf("%dv%d",size0,size1))
        battleArgs = []
        trainers.each do |t|
          battleArgs.push([t[1][0],t[1][2],t[1][3],t[1][1]])
        end
        pbTrainerBattleCore(*battleArgs)
        break
      elsif trainerCmd==trainerCmds.length-2   # Set opponent side size
        if trainers.length==0 || (trainers.length==1 && trainers[0][1][2].length==1)
          pbMessage(_INTL("没有选择训练家，或该训练家只有一只宝可梦。"))
          next
        end
        maxVal = 2
        maxVal = 3 if trainers.length>=3 ||
                      (trainers.length==2 && trainers[0][1][2].length>=2) ||
                      trainers[0][1][2].length>=3
        params = ChooseNumberParams.new
        params.setRange(1,maxVal)
        params.setInitialValue(size1)
        params.setCancelValue(0)
        newSize = pbMessageChooseNumber(
           _INTL("选择对方上场数量（最大 {1}）。",maxVal),params)
        size1 = newSize if newSize>0
      elsif trainerCmd==trainerCmds.length-3   # Set player side size
        if !pbCanDoubleBattle?
          pbMessage(_INTL("你只有一只宝可梦。"))
          next
        end
        maxVal = (pbCanTripleBattle?) ? 3 : 2
        params = ChooseNumberParams.new
        params.setRange(1,maxVal)
        params.setInitialValue(size0)
        params.setCancelValue(0)
        newSize = pbMessageChooseNumber(
           _INTL("选择己方上场数量（最大 {1}）。",maxVal),params)
        size0 = newSize if newSize>0
      elsif trainerCmd==trainerCmds.length-4   # Add trainer
        battle = pbListScreen(_INTL("选择训练家"),TrainerBattleLister.new(0,false))
        if battle
          trainerdata = battle[1]
          tr = pbLoadTrainer(trainerdata[0],trainerdata[1],trainerdata[4])
          trainers.push([battle[0],tr])
        end
      else                                     # Edit a trainer
        if pbConfirmMessage(_INTL("要修改这个训练家吗？"))
          battle = pbListScreen(_INTL("选择训练家"),
             TrainerBattleLister.new(trainers[trainerCmd][0],false))
          if battle
            trainerdata = battle[1]
            tr = pbLoadTrainer(trainerdata[0],trainerdata[1],trainerdata[4])
            trainers[trainerCmd] = [battle[0],tr]
          end
        elsif pbConfirmMessage(_INTL("要删除这个训练家吗？"))
          trainers[trainerCmd] = nil
          trainers.compact!
        end
      end
    end
  when "togglelogging"
    $INTERNAL = !$INTERNAL
    pbMessage(_INTL("战斗调试日志会生成在 Data 文件夹里。")) if $INTERNAL
    pbMessage(_INTL("不再生成战斗调试日志。")) if !$INTERNAL
  when "resettrainers"
    if $game_map
      for event in $game_map.events.values
        if event.name[/trainer/i]
          $game_self_switches[[$game_map.map_id,event.id,"A"]] = false
          $game_self_switches[[$game_map.map_id,event.id,"B"]] = false
        end
      end
      $game_map.need_refresh = true
      pbMessage(_INTL("本地图所有训练家已重置。"))
    else
      pbMessage(_INTL("这里不能使用这个指令。"))
    end
  when "readyrematches"
    if !$PokemonGlobal.phoneNumbers || $PokemonGlobal.phoneNumbers.length==0
      pbMessage(_INTL("电话里没有训练家。"))
    else
      for i in $PokemonGlobal.phoneNumbers
        if i.length==8 # A trainer with an event
          i[4] = 2
          pbSetReadyToBattle(i)
        end
      end
      pbMessage(_INTL("电话里的所有训练家现在都可以再战了。"))
    end
  when "roamers"
    pbDebugRoamers
  #=============================================================================
  # Item options
  #=============================================================================
  when "additem"
    pbListScreenBlock(_INTL("添加道具"),ItemLister.new(0)) { |button,item|
      if button==Input::C && item && item>0
        params = ChooseNumberParams.new
        params.setRange(1,BAG_MAX_PER_SLOT)
        params.setInitialValue(1)
        params.setCancelValue(0)
        qty = pbMessageChooseNumber(_INTL("选择道具数量。"),params)
        if qty>0
          $PokemonBag.pbStoreItem(item,qty)
          pbMessage(_INTL("给予了 {1} 个 {2}。",qty,PBItems.getName(item)))
        end
      end
    }
  when "fillbag"
    params = ChooseNumberParams.new
    params.setRange(1,BAG_MAX_PER_SLOT)
    params.setInitialValue(1)
    params.setCancelValue(0)
    qty = pbMessageChooseNumber(_INTL("选择道具数量。"),params)
    if qty>0
      itemconsts = []
      for i in PBItems.constants
        itemconsts.push(PBItems.const_get(i))
      end
      itemconsts.sort! { |a,b| a<=>b }
      for i in itemconsts
        $PokemonBag.pbStoreItem(i,qty)
      end
      pbMessage(_INTL("背包里每种道具都装入了 {1} 个。",qty))
    end
  when "emptybag"
    $PokemonBag.clear
    pbMessage(_INTL("背包已清空。"))
  #=============================================================================
  # Pokémon options
  #=============================================================================
  when "addpokemon"
    species = pbChooseSpeciesList
    if species!=0
      params = ChooseNumberParams.new
      params.setRange(1,PBExperience.maxLevel)
      params.setInitialValue(5)
      params.setCancelValue(0)
      level = pbMessageChooseNumber(_INTL("设置该宝可梦的等级。"),params)
      if level>0
        pbAddPokemon(species,level)
      end
    end
  when "demoparty"
    pbCreatePokemon
    pbMessage(_INTL("已用演示宝可梦填满队伍。"))
  when "healparty"
    for i in $Trainer.party
      i.heal
    end
    pbMessage(_INTL("你的宝可梦已完全回复。"))
  when "quickhatch"
    for pokemon in $Trainer.party
      pokemon.eggsteps = 1 if pokemon.egg?
    end
    pbMessage(_INTL("队伍里的所有蛋现在只需 1 步就能孵化。"))
  when "fillboxes"
    $Trainer.formseen     = [] if !$Trainer.formseen
    $Trainer.formlastseen = [] if !$Trainer.formlastseen
    added = 0; completed = true
    speciesData = pbLoadSpeciesData
    formdata    = pbLoadFormToSpecies
    for i in 1..PBSpecies.maxValue
      if added>=NUM_STORAGE_BOXES*30
        completed = false; break
      end
      cname = getConstantName(PBSpecies,i) rescue nil
      next if !cname
      pkmn = pbNewPkmn(i,50)
      $PokemonStorage[(i-1)/$PokemonStorage.maxPokemon(0),
                      (i-1)%$PokemonStorage.maxPokemon(0)] = pkmn
      # Record all forms of this Pokémon as seen and owned
      $Trainer.seen[i]  = true
      $Trainer.owned[i] = true
      $Trainer.formseen[i] = [[],[]]
      formdata[i] = [i] if !formdata[i]
      for form in 0...formdata[i].length
        next if !formdata[i][form] || formdata[i][form]==0
        fSpecies = pbGetFSpeciesFromForm(i,form)
        formname = pbGetMessage(MessageTypes::FormNames,fSpecies)
        genderRate = speciesData[i][SpeciesGenderRate] || 0
        gender = (genderRate==PBGenderRates::AlwaysFemale) ? 1 : 0
        if form==0
          case genderRate
          when PBGenderRates::AlwaysMale,
               PBGenderRates::AlwaysFemale,
               PBGenderRates::Genderless
            $Trainer.formseen[i][gender][form] = true
            $Trainer.formlastseen[i] = [gender,form]
          else   # Both male and female
            $Trainer.formseen[i][0][form] = true
            $Trainer.formseen[i][1][form] = true
            $Trainer.formlastseen[i] = [0,form]
          end
        elsif formname && formname!=""
          $Trainer.formseen[i][gender][form] = true
        end
      end
      added += 1
    end
    pbMessage(_INTL("仓库已用每种各 1 只宝可梦填满。"))
    if !completed
      pbMessage(_INTL("注意：寄存空间（{1} 个 30 格仓库）少于宝可梦种类数。",NUM_STORAGE_BOXES))
    end
  when "clearboxes"
    for i in 0...$PokemonStorage.maxBoxes
      for j in 0...$PokemonStorage.maxPokemon(i)
        $PokemonStorage[i,j] = nil
      end
    end
    pbMessage(_INTL("仓库已清空。"))
  when "openstorage"
    pbFadeOutIn {
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
      badgecmds.push(_INTL("全部给予"))
      badgecmds.push(_INTL("全部移除"))
      for i in 0...24
        badgecmds.push(_INTL("{1} 徽章 {2}",$Trainer.badges[i] ? "[Y]" : "[  ]",i+1))
      end
      badgecmd = pbShowCommands(nil,badgecmds,-1,badgecmd)
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
    params.setRange(0,MAX_MONEY)
    params.setDefaultValue($Trainer.money)
    $Trainer.money = pbMessageChooseNumber(_INTL("设置玩家的金钱。"),params)
    pbMessage(_INTL("你现在有 ${1}。",$Trainer.money.to_s_formatted))
  when "setcoins"
    params = ChooseNumberParams.new
    params.setRange(0,MAX_COINS)
    params.setDefaultValue($PokemonGlobal.coins)
    $PokemonGlobal.coins = pbMessageChooseNumber(_INTL("设置玩家的金币数量。"),params)
    pbMessage(_INTL("你现在有 {1} 代币。",$PokemonGlobal.coins.to_s_formatted))
  when "toggleshoes"
    $PokemonGlobal.runningShoes = !$PokemonGlobal.runningShoes
    pbMessage(_INTL("已给予跑步鞋。")) if $PokemonGlobal.runningShoes
    pbMessage(_INTL("已失去跑步鞋。")) if !$PokemonGlobal.runningShoes
  when "togglepokegear"
    $Trainer.pokegear = !$Trainer.pokegear
    pbMessage(_INTL("已给予宝可钟。")) if $Trainer.pokegear
    pbMessage(_INTL("已失去宝可钟。")) if !$Trainer.pokegear
  when "dexlists"
    dexescmd = 0
    loop do
      dexescmds = []
      dexescmds.push(_INTL("拥有图鉴：{1}",$Trainer.pokedex ? "[YES]" : "[NO]"))
      d = pbDexNames
      for i in 0...d.length
        name = d[i]
        name = name[0] if name.is_a?(Array)
        dexindex = i
        unlocked = $PokemonGlobal.pokedexUnlocked[dexindex]
        dexescmds.push(_INTL("{1} {2}",unlocked ? "[Y]" : "[  ]",name))
      end
      dexescmd = pbShowCommands(nil,dexescmds,-1,dexescmd)
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
      pbMessage(_INTL("只定义了一个主角。"))
    else
      params = ChooseNumberParams.new
      params.setRange(0,limit-1)
      params.setDefaultValue($PokemonGlobal.playerID)
      newid = pbMessageChooseNumber(_INTL("选择新的主角形象。"),params)
      if newid!=$PokemonGlobal.playerID
        pbChangePlayer(newid)
        pbMessage(_INTL("主角形象已更换。"))
      end
    end
  when "changeoutfit"
    oldoutfit = $Trainer.outfit
    params = ChooseNumberParams.new
    params.setRange(0,99)
    params.setDefaultValue(oldoutfit)
    $Trainer.outfit = pbMessageChooseNumber(_INTL("设置主角装扮。"),params)
    pbMessage(_INTL("主角装扮已更换。")) if $Trainer.outfit!=oldoutfit
  when "renameplayer"
    trname = pbEnterPlayerName("Your name?",0,MAX_PLAYER_NAME_SIZE,$Trainer.name)
    if trname=="" && pbConfirmMessage(_INTL("给自己取个默认名字吗？"))
      trainertype = pbGetPlayerTrainerType
      gender      = pbGetTrainerTypeGender(trainertype)
      trname      = pbSuggestTrainerName(gender)
    end
    if trname==""
      pbMessage(_INTL("玩家的名字仍为 {1}。",$Trainer.name))
    else
      $Trainer.name = trname
      pbMessage(_INTL("玩家的名字已改为 {1}。",$Trainer.name))
    end
  when "randomid"
    $Trainer.id = rand(256)
    $Trainer.id |= rand(256)<<8
    $Trainer.id |= rand(256)<<16
    $Trainer.id |= rand(256)<<24
    pbMessage(_INTL("玩家的 ID 已改为 {1}（完整 ID：{2}）。",$Trainer.publicID,$Trainer.id))
  #=============================================================================
  # Information editors
  #=============================================================================
  when "setmetadata"
    pbMetadataScreen(pbDefaultMap)
    pbClearData
  when "mapconnections"
    pbFadeOutIn { pbConnectionsEditor }
  when "terraintags"
    pbFadeOutIn { pbTilesetScreen }
  when "setencounters"
    encdata = pbLoadEncountersData
    map = pbDefaultMap
    loop do
      map = pbListScreen(_INTL("设置遭遇表"),MapLister.new(map))
      break if map<=0
      pbEncounterEditorMap(encdata,map)
    end
    save_data(encdata,"Data/encounters.dat")
    pbClearData
    pbSaveEncounterData
  when "trainertypes"
    pbFadeOutIn { pbTrainerTypeEditor }
  when "edittrainers"
    pbFadeOutIn { pbTrainerBattleEditor }
  when "edititems"
    pbFadeOutIn { pbItemEditor }
  when "editpokemon"
    pbFadeOutIn { pbPokemonEditor }
  when "editdexes"
    pbFadeOutIn { pbRegionalDexEditorMain }
  when "positionsprites"
    pbFadeOutIn {
      sp = SpritePositioner.new
      sps = SpritePositionerScreen.new(sp)
      sps.pbStart
    }
  when "autopositionsprites"
    if pbConfirmMessage(_INTL("确定要重新排列所有图块吗？"))
      msgwindow = pbCreateMessageWindow
      pbMessageDisplay(msgwindow,_INTL("正在重新排列所有图块，请稍候。"),false)
      Graphics.update
      pbAutoPositionAll
      pbDisposeMessageWindow(msgwindow)
    end
  when "animeditor"
    pbFadeOutIn { pbAnimationEditor }
  when "animorganiser"
    pbFadeOutIn { pbAnimationsOrganiser }
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
    msgwindow = pbCreateMessageWindow
    pbCompileAllData(true) { |msg| pbMessageDisplay(msgwindow,msg,false) }
    pbMessageDisplay(msgwindow,_INTL("全部游戏数据已编译。"))
    pbDisposeMessageWindow(msgwindow)
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
  sprites["textbox"] = pbCreateMessageWindow
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
          pbPlayCancelSE
          commands.currentList = parent[0]
          cmdwindow.commands = commands.list
          cmdwindow.index = parent[1]
          refresh = true
        else
          ret = -1
          break
        end
      elsif Input.trigger?(Input::C)
        pbPlayDecisionSE
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
  pbPlayCloseMenuSE
  pbFadeOutAndHide(sprites)
  pbDisposeMessageWindow(sprites["textbox"])
  pbDisposeSpriteHash(sprites)
  viewport.dispose
end
