class PokemonDataCopy
  attr_accessor :dataOldHash
  attr_accessor :dataNewHash
  attr_accessor :dataTime
  attr_accessor :data

  def crc32(x)
    return Zlib::crc32(x)
  end

  def readfile(filename)
    File.open(filename, "rb"){|f|
       f.read
    }
  end

  def writefile(str,filename)
    File.open(filename, "wb"){|f|
       f.write(str)
    }
  end

  def filetime(filename)
    File.open(filename, "r"){|f|
       f.mtime
    }
  end

  def initialize(data,datasave)
    @datafile=data
    @datasave=datasave
    @data=readfile(@datafile)
    @dataOldHash=crc32(@data)
    @dataTime=filetime(@datafile)
  end

  def changed?
    ts=readfile(@datafile)
    tsDate=filetime(@datafile)
    tsHash=crc32(ts)
    return tsHash!=@dataNewHash && tsHash!=@dataOldHash && tsDate > @dataTime
  end

  def save(newtilesets)
    newdata=Marshal.dump(newtilesets)
    if !changed?
      @data=newdata
      @dataNewHash=crc32(newdata)
      writefile(newdata,@datafile)
    else
      @dataOldHash=crc32(@data)
      @dataNewHash=crc32(newdata)
      @dataTime=filetime(@datafile)
      @data=newdata
      writefile(newdata,@datafile)
    end
    save_data(self,@datasave)
  end
end



class PokemonDataWrapper
  attr_reader :data

  def initialize(file,savefile,prompt)
    @savefile=savefile
    @file=file
    if pbRgssExists?(@savefile)
      @ts=load_data(@savefile)
      if !@ts.changed? || prompt.call==true
        @data=Marshal.load(StringInput.new(@ts.data))
      else
        @ts=PokemonDataCopy.new(@file,@savefile)
        @data=load_data(@file)
      end
    else
      @ts=PokemonDataCopy.new(@file,@savefile)
      @data=load_data(@file)
    end
  end

  def save
    @ts.save(@data)
  end
end



def pbMapTree
  mapinfos=pbLoadRxData("Data/MapInfos")
  maplevels=[]
  retarray=[]
  for i in mapinfos.keys
    info=mapinfos[i]
    level=-1
    while info
      info=mapinfos[info.parent_id]
      level+=1
    end
    if level>=0
      info=mapinfos[i]
      maplevels.push([i,level,info.parent_id,info.order])
    end
  end
  maplevels.sort!{|a,b|
     next a[1]<=>b[1] if a[1]!=b[1] # level
     next a[2]<=>b[2] if a[2]!=b[2] # parent ID
     next a[3]<=>b[3] # order
  }
  stack=[]
  stack.push(0,0)
  while stack.length>0
    parent = stack[stack.length-1]
    index = stack[stack.length-2]
    if index>=maplevels.length
      stack.pop
      stack.pop
      next
    end
    maplevel=maplevels[index]
    stack[stack.length-2]+=1
    if maplevel[2]!=parent
      stack.pop
      stack.pop
      next
    end
    retarray.push([maplevel[0],mapinfos[maplevel[0]].name,maplevel[1]])
    for i in index+1...maplevels.length
      if maplevels[i][2]==maplevel[0]
        stack.push(i)
        stack.push(maplevel[0])
        break
      end
    end
  end
  return retarray
end

def pbExtractText
  msgwindow=Kernel.pbCreateMessageWindow
  Kernel.pbMessageDisplay(msgwindow,_INTL("请稍候。"))
  MessageTypes.extract("intl.txt")
  Kernel.pbMessageDisplay(msgwindow,
     _INTL("游戏内全部文本已导出并保存到 intl.txt。\1"))
  Kernel.pbMessageDisplay(msgwindow,
     _INTL("要为某种语言本地化文本，请翻译文件里每隔一行的内容。\1"))
  Kernel.pbMessageDisplay(msgwindow,
     _INTL("翻译完成后，选择「Compile Text（编译文本）」。"))
  Kernel.pbDisposeMessageWindow(msgwindow)
end

def pbCompileTextUI
  msgwindow=Kernel.pbCreateMessageWindow
  Kernel.pbMessageDisplay(msgwindow,_INTL("请稍候。"))
  begin
    pbCompileText
    Kernel.pbMessageDisplay(msgwindow,
       _INTL("文本编译成功，已保存到 intl.dat。"))
    Kernel.pbMessageDisplay(msgwindow,
       _INTL("要在游戏中使用该文件，请把它换个名字放进 Data 文件夹，并在 Settings 脚本里编辑 LANGUAGES 数组。"))
    rescue RuntimeError
    Kernel.pbMessageDisplay(msgwindow,
       _INTL("编译文本失败：{1}",$!.message))
  end
  Kernel.pbDisposeMessageWindow(msgwindow)
end



class CommandList
  def initialize
    @commandHash={}
    @commands=[]
  end

  def getCommand(index)
    for key in @commandHash.keys
      return key if @commandHash[key]==index
    end
    return nil
  end

  def add(key,value)
    @commandHash[key]=@commands.length
    @commands.push(value)
  end

  def list
    @commands.clone
  end
end



def pbDefaultMap()
  return $game_map.map_id if $game_map
  return $data_system.edit_map_id if $data_system
  return 0
end

def pbWarpToMap()
  mapid=pbListScreen(_INTL("传送到地图"),MapLister.new(pbDefaultMap()))
  if mapid>0
    map=Game_Map.new
    map.setup(mapid)
    success=false
    x=0
    y=0
    100.times do
      x=rand(map.width)
      y=rand(map.height)
      next if !map.passableStrict?(x,y,$game_player)
      blocked=false
      for event in map.events.values
        if event.x == x && event.y == y && !event.through
          blocked=true if self != $game_player || event.character_name != ""
        end
      end
      next if blocked
      success=true
      break
    end
    if !success
      x=rand(map.width)
      y=rand(map.height)
    end
    return [mapid,x,y]
  end
  return nil
end

def pbDebugMenu
  viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
  viewport.z=99999
  sprites={}
  commands=CommandList.new
  commands.add("switches",_INTL("开关"))
  commands.add("variables",_INTL("变量"))
  commands.add("refreshmap",_INTL("刷新地图"))
  commands.add("warp",_INTL("传送至地图"))
  commands.add("healparty",_INTL("恢复全队"))
  commands.add("additem",_INTL("添加道具"))
  commands.add("fillbag",_INTL("装满背包"))
  commands.add("clearbag",_INTL("清空背包"))
  commands.add("addpokemon",_INTL("添加宝可梦"))
  commands.add("fillboxes",_INTL("填满寄存箱"))
  commands.add("clearboxes",_INTL("清空寄存箱"))
  commands.add("usepc",_INTL("使用电脑"))
  commands.add("setplayer",_INTL("设置玩家角色"))
  commands.add("renameplayer",_INTL("重命名玩家"))
  commands.add("randomid",_INTL("随机玩家的ID"))
  commands.add("changeoutfit",_INTL("更换主角装扮"))
  commands.add("setmoney",_INTL("设置金钱"))
  commands.add("setcoins",_INTL("设置代币"))
  commands.add("setbadges",_INTL("设置徽章"))
  commands.add("demoparty",_INTL("给予演示队伍"))
  commands.add("toggleshoes",_INTL("切换跑步鞋归属"))
  commands.add("togglepokegear",_INTL("切换宝可钟归属"))
  commands.add("togglepokedex",_INTL("切换图鉴归属"))
  commands.add("dexlists",_INTL("图鉴列表显示设置"))
  commands.add("readyrematches",_INTL("准备电话再战"))
  commands.add("mysterygift",_INTL("管理神秘礼物"))
  commands.add("daycare",_INTL("培育屋选项……"))
  commands.add("quickhatch",_INTL("快速孵化"))
  commands.add("roamerstatus",_INTL("乱步宝可梦状态"))
  commands.add("roam",_INTL("推进乱步"))
  commands.add("setencounters",_INTL("设置遭遇表")) 
  commands.add("setmetadata",_INTL("设置 metadata")) 
  commands.add("terraintags",_INTL("设置地形标记"))
  commands.add("trainertypes",_INTL("编辑训练家类型"))
  commands.add("resettrainers",_INTL("重置训练家"))
  commands.add("testwildbattle",_INTL("测试野生对战"))
  commands.add("testdoublewildbattle",_INTL("测试双打野生战斗"))
  commands.add("testtrainerbattle",_INTL("测试训练家对战"))
  commands.add("testdoubletrainerbattle",_INTL("测试双打训练家战斗"))
  commands.add("relicstone",_INTL("遗迹之石"))
  commands.add("purifychamber",_INTL("净化室"))
  commands.add("extracttext",_INTL("提取文本"))
  commands.add("compiletext",_INTL("编译文本"))
  commands.add("compiledata",_INTL("编译数据"))
  commands.add("mapconnections",_INTL("地图连接"))
  commands.add("animeditor",_INTL("动画编辑器"))
  commands.add("debugconsole",_INTL("调试控制台"))
  commands.add("togglelogging",_INTL("切换战斗日志"))
  sprites["cmdwindow"]=Window_CommandPokemonEx.new(commands.list)
  cmdwindow=sprites["cmdwindow"]
  cmdwindow.viewport=viewport
  cmdwindow.resizeToFit(cmdwindow.commands)
  cmdwindow.height=Graphics.height if cmdwindow.height>Graphics.height
  cmdwindow.x=0
  cmdwindow.y=0
  cmdwindow.visible=true
  pbFadeInAndShow(sprites)
  ret=-1
  loop do
    loop do
      cmdwindow.update
      Graphics.update
      Input.update
      if Input.trigger?(Input::B)
        ret=-1
        break
      end
      if Input.trigger?(Input::C)
        ret=cmdwindow.index
        break
      end
    end
    break if ret==-1
    cmd=commands.getCommand(ret)
    if cmd=="switches"
      pbFadeOutIn(99999) { pbDebugScreen(0) }
    elsif cmd=="variables"
      pbFadeOutIn(99999) { pbDebugScreen(1) }
    elsif cmd=="refreshmap"
      $game_map.need_refresh = true
      Kernel.pbMessage(_INTL("地图将刷新。"))
    elsif cmd=="warp"
      map=pbWarpToMap()
      if map
        pbFadeOutAndHide(sprites)
        pbDisposeSpriteHash(sprites)
        viewport.dispose
        if $scene.is_a?(Scene_Map)
          $game_temp.player_new_map_id=map[0]
          $game_temp.player_new_x=map[1]
          $game_temp.player_new_y=map[2]
          $game_temp.player_new_direction=2
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
        return
      end
    elsif cmd=="healparty"
      for i in $Trainer.party
        i.heal
      end
      Kernel.pbMessage(_INTL("你的宝可梦已回复。"))
    elsif cmd=="additem"
      item=pbListScreen(_INTL("添加道具"),ItemLister.new(0))
      if item && item>0
        params=ChooseNumberParams.new
        params.setRange(1,BAGMAXPERSLOT)
        params.setInitialValue(1)
        params.setCancelValue(0)
        qty=Kernel.pbMessageChooseNumber(
           _INTL("选择道具数量。"),params
        )
        if qty>0
          if qty==1
            Kernel.pbReceiveItem(item)
          else
            Kernel.pbMessage(_INTL("道具已添加。"))
            $PokemonBag.pbStoreItem(item,qty)
          end
        end
      end
    elsif cmd=="fillbag"
      params=ChooseNumberParams.new
      params.setRange(1,BAGMAXPERSLOT)
      params.setInitialValue(1)
      params.setCancelValue(0)
      qty=Kernel.pbMessageChooseNumber(
         _INTL("选择道具数量。"),params
      )
      if qty>0
        itemconsts=[]
        for i in PBItems.constants
          itemconsts.push(PBItems.const_get(i))
        end
        itemconsts.sort!{|a,b| a<=>b}
        for i in itemconsts
          $PokemonBag.pbStoreItem(i,qty)
        end
        Kernel.pbMessage(_INTL("背包里每种道具都装入了 {1} 个。",qty))
      end
    elsif cmd=="clearbag"
      $PokemonBag.clear
      Kernel.pbMessage(_INTL("背包已清空。"))
    elsif cmd=="addpokemon"
      species=pbChooseSpeciesOrdered(1)
      if species!=0
        params=ChooseNumberParams.new
        params.setRange(1,PBExperience::MAXLEVEL)
        params.setInitialValue(5)
        params.setCancelValue(0)
        level=Kernel.pbMessageChooseNumber(
           _INTL("设置该宝可梦的等级。"),params)
        if level>0
          pbAddPokemon(species,level)
        end
      end
    elsif cmd=="fillboxes"
      $Trainer.formseen=[] if !$Trainer.formseen
      $Trainer.formlastseen=[] if !$Trainer.formlastseen
      added=0; completed=true
      for i in 1..PBSpecies.maxValue
        if added>=STORAGEBOXES*30
          completed=false; break
        end
        cname=getConstantName(PBSpecies,i) rescue nil
        next if !cname
        pkmn=PokeBattle_Pokemon.new(i,50,$Trainer)
        $PokemonStorage[(i-1)/$PokemonStorage.maxPokemon(0),
                        (i-1)%$PokemonStorage.maxPokemon(0)]=pkmn
        $Trainer.seen[i]=true
        $Trainer.owned[i]=true
        $Trainer.formlastseen[i]=[] if !$Trainer.formlastseen[i]
        $Trainer.formlastseen[i]=[0,0] if $Trainer.formlastseen[i]==[]
        $Trainer.formseen[i]=[[],[]] if !$Trainer.formseen[i]
        for j in 0..27
          $Trainer.formseen[i][0][j]=true
          $Trainer.formseen[i][1][j]=true
        end
        added+=1
      end
      Kernel.pbMessage(_INTL("仓库已用每种各 1 只宝可梦填满。"))
      if !completed
        Kernel.pbMessage(_INTL("注意：寄存空间（{1} 个 30 格仓库）少于宝可梦种类数。",STORAGEBOXES))
      end
    elsif cmd=="clearboxes"
      for i in 0...$PokemonStorage.maxBoxes
        for j in 0...$PokemonStorage.maxPokemon(i)
          $PokemonStorage[i,j]=nil
        end
      end
      Kernel.pbMessage(_INTL("仓库已清空。"))
    elsif cmd=="usepc"
      pbPokeCenterPC
    elsif cmd=="setplayer"
      limit=0
      for i in 0...8
        meta=pbGetMetadata(0,MetadataPlayerA+i)
        if !meta
          limit=i
          break
        end
      end
      if limit<=1
        Kernel.pbMessage(_INTL("只定义了一个主角。"))
      else
        params=ChooseNumberParams.new
        params.setRange(0,limit-1)
        params.setDefaultValue($PokemonGlobal.playerID)
        newid=Kernel.pbMessageChooseNumber(
           _INTL("选择新的主角形象。"),params)
        if newid!=$PokemonGlobal.playerID
          pbChangePlayer(newid)
          Kernel.pbMessage(_INTL("主角形象已更换。"))
        end
      end
    elsif cmd=="renameplayer"
      trname=pbEnterPlayerName("Your name?",0,7,$Trainer.name)
      if trname==""
        trainertype=pbGetPlayerTrainerType
        gender=pbGetTrainerTypeGender(trainertype) 
        trname=pbSuggestTrainerName(gender)
      end
      $Trainer.name=trname
      Kernel.pbMessage(_INTL("玩家的名字已改为 {1}。",$Trainer.name))
    elsif cmd=="randomid"
      $Trainer.id=rand(256)
      $Trainer.id|=rand(256)<<8
      $Trainer.id|=rand(256)<<16
      $Trainer.id|=rand(256)<<24
      Kernel.pbMessage(_INTL("玩家的 ID 已改为 {1}（2）。",$Trainer.publicID,$Trainer.id))
    elsif cmd=="changeoutfit"
      oldoutfit=$Trainer.outfit
      params=ChooseNumberParams.new
      params.setRange(0,99)
      params.setDefaultValue(oldoutfit)
      $Trainer.outfit=Kernel.pbMessageChooseNumber(_INTL("设置主角装扮。"),params)
      Kernel.pbMessage(_INTL("主角装扮已更换。")) if $Trainer.outfit!=oldoutfit
    elsif cmd=="setmoney"
      params=ChooseNumberParams.new
      params.setMaxDigits(6)
      params.setDefaultValue($Trainer.money)
      $Trainer.money=Kernel.pbMessageChooseNumber(
         _INTL("设置玩家的金钱。"),params)
      Kernel.pbMessage(_INTL("你现在有 ${1}。",$Trainer.money))
    elsif cmd=="setcoins"
      params=ChooseNumberParams.new
      params.setRange(0,MAXCOINS)
      params.setDefaultValue($PokemonGlobal.coins)
      $PokemonGlobal.coins=Kernel.pbMessageChooseNumber(
         _INTL("设置玩家的金币数量。"),params)
      Kernel.pbMessage(_INTL("你现在有 {1} 代币。",$PokemonGlobal.coins))
    elsif cmd=="setbadges"
      badgecmd=0
      loop do
        badgecmds=[]
        for i in 0...32
          badgecmds.push(_INTL("{1} 徽章 {2}",$Trainer.badges[i] ? "[Y]" : "[  ]",i+1))
        end
        badgecmd=Kernel.pbShowCommands(nil,badgecmds,-1,badgecmd)
        break if badgecmd<0
        $Trainer.badges[badgecmd]=!$Trainer.badges[badgecmd]
      end
    elsif cmd=="demoparty"
      pbCreatePokemon
      Kernel.pbMessage(_INTL("已用演示宝可梦填满队伍。"))
    elsif cmd=="toggleshoes"
      $PokemonGlobal.runningShoes=!$PokemonGlobal.runningShoes
      Kernel.pbMessage(_INTL("已给予跑步鞋。")) if $PokemonGlobal.runningShoes
      Kernel.pbMessage(_INTL("已失去跑步鞋。")) if !$PokemonGlobal.runningShoes
    elsif cmd=="togglepokegear"
      $Trainer.pokegear=!$Trainer.pokegear
      Kernel.pbMessage(_INTL("已给予宝可钟。")) if $Trainer.pokegear
      Kernel.pbMessage(_INTL("已失去宝可钟。")) if !$Trainer.pokegear
    elsif cmd=="togglepokedex"
      $Trainer.pokedex=!$Trainer.pokedex
      Kernel.pbMessage(_INTL("已给予图鉴。")) if $Trainer.pokedex
      Kernel.pbMessage(_INTL("已失去图鉴。")) if !$Trainer.pokedex
    elsif cmd=="dexlists"
      dexescmd=0
      loop do
        dexescmds=[]
        d=pbDexNames
        for i in 0...d.length
          name=d[i]
          name=name[0] if name.is_a?(Array)
          dexindex=i
          unlocked=$PokemonGlobal.pokedexUnlocked[dexindex]
          dexescmds.push(_INTL("{1} {2}",unlocked ? "[Y]" : "[  ]",name))
        end
        dexescmd=Kernel.pbShowCommands(nil,dexescmds,-1,dexescmd)
        break if dexescmd<0
        dexindex=dexescmd
        if $PokemonGlobal.pokedexUnlocked[dexindex]
          pbLockDex(dexindex)
        else
          pbUnlockDex(dexindex)
        end
      end
    elsif cmd=="readyrematches"
      if !$PokemonGlobal.phoneNumbers || $PokemonGlobal.phoneNumbers.length==0
        Kernel.pbMessage(_INTL("电话里没有训练家。"))
      else
        for i in $PokemonGlobal.phoneNumbers
          if i.length==8 # A trainer with an event
            i[4]=2
            pbSetReadyToBattle(i)
          end
        end
        Kernel.pbMessage(_INTL("电话里的所有训练家现在都可以再战了。"))
      end
    elsif cmd=="mysterygift"
      pbManageMysteryGifts
    elsif cmd=="daycare"
      daycarecmd=0
      loop do
        daycarecmds=[
           _INTL("查看详情"),
           _INTL("寄存宝可梦"),
           _INTL("取回宝可梦"),
           _INTL("生成蛋"),
           _INTL("领取蛋"),
           _INTL("处理掉蛋")
        ]
        daycarecmd=Kernel.pbShowCommands(nil,daycarecmds,-1,daycarecmd)
        break if daycarecmd<0
        case daycarecmd
        when 0 # Summary
          if $PokemonGlobal.daycare
            num=pbDayCareDeposited
            Kernel.pbMessage(_INTL("培育屋里有 {1} 只宝可梦。",num))
            if num>0
              txt=""
              for i in 0...num
                next if !$PokemonGlobal.daycare[i][0]
                pkmn=$PokemonGlobal.daycare[i][0]
                initlevel=$PokemonGlobal.daycare[i][1]
                gender=[_INTL("♂"),_INTL("♀"),_INTL("无性别")][pkmn.gender]
                txt+=_INTL("{1}）{2}（{3}），Lv.{4}（寄存时 Lv.{5}）",
                   i,pkmn.name,gender,pkmn.level,initlevel)
                txt+="\n" if i<num-1
              end
              Kernel.pbMessage(txt)
            end
            if $PokemonGlobal.daycareEgg==1
              Kernel.pbMessage(_INTL("有一颗蛋等着被领走。"))
            elsif pbDayCareDeposited==2
              if pbDayCareGetCompat==0
                Kernel.pbMessage(_INTL("寄存的宝可梦无法繁殖。"))
              else
                Kernel.pbMessage(_INTL("寄存的宝可梦可以繁殖。"))
              end
            end
          end
        when 1 # Deposit Pokémon
          if pbEggGenerated?
            Kernel.pbMessage(_INTL("有蛋待领，无法寄存宝可梦。"))
          elsif pbDayCareDeposited==2
            Kernel.pbMessage(_INTL("已经寄存了 2 只宝可梦。"))
          elsif $Trainer.party.length==0
            Kernel.pbMessage(_INTL("队伍为空，无法寄存宝可梦。"))
          else
            pbChooseNonEggPokemon(1,3)
            if pbGet(1)>=0
              pbDayCareDeposit(pbGet(1))
              Kernel.pbMessage(_INTL("已寄存 {1}。",pbGet(3)))
            end
          end
        when 2 # Withdraw Pokémon
          if pbEggGenerated?
            Kernel.pbMessage(_INTL("有蛋待领，无法取回宝可梦。"))
          elsif pbDayCareDeposited==0
            Kernel.pbMessage(_INTL("培育屋里没有宝可梦。"))
          elsif $Trainer.party.length>=6
            Kernel.pbMessage(_INTL("队伍已满，无法取回宝可梦。"))
          else
            pbDayCareChoose(_INTL("要取回哪一只？"),1)
            if pbGet(1)>=0
              pbDayCareGetDeposited(pbGet(1),3,4)
              pbDayCareWithdraw(pbGet(1))
              Kernel.pbMessage(_INTL("已取出 {1}。",pbGet(3)))
            end
          end
        when 3 # Generate egg
          if $PokemonGlobal.daycareEgg==1
            Kernel.pbMessage(_INTL("已经有一颗蛋在等着了。"))
          elsif pbDayCareDeposited!=2
            Kernel.pbMessage(_INTL("培育屋里没有 2 只宝可梦。"))
          elsif pbDayCareGetCompat==0
            Kernel.pbMessage(_INTL("培育屋里的宝可梦无法繁殖。"))
          else
            $PokemonGlobal.daycareEgg=1
            Kernel.pbMessage(_INTL("培育屋现在有一颗蛋在等着。"))
          end
        when 4 # Collect egg
          if $PokemonGlobal.daycareEgg!=1
            Kernel.pbMessage(_INTL("没有可领取的蛋。"))
          elsif $Trainer.party.length>=6
            Kernel.pbMessage(_INTL("队伍已满，无法领取蛋。"))
          else
            pbDayCareGenerateEgg
            $PokemonGlobal.daycareEgg=0
            $PokemonGlobal.daycareEggSteps=0
            Kernel.pbMessage(_INTL("领取了 {1} 的蛋。",
               PBSpecies.getName($Trainer.party[$Trainer.party.length-1].species)))
          end
        when 5 # Dispose egg
          if $PokemonGlobal.daycareEgg!=1
            Kernel.pbMessage(_INTL("没有可领取的蛋。"))
          else
            $PokemonGlobal.daycareEgg=0
            $PokemonGlobal.daycareEggSteps=0
            Kernel.pbMessage(_INTL("已处理掉那颗蛋。"))
          end
        end
      end
    elsif cmd=="quickhatch"
      for pokemon in $Trainer.party
        pokemon.eggsteps=1 if pokemon.isEgg?
      end
      Kernel.pbMessage(_INTL("队伍里的所有蛋现在只需 1 步就能孵化。"))
    elsif cmd=="roamerstatus"
      if RoamingSpecies.length==0
        Kernel.pbMessage(_INTL("没有定义乱步宝可梦。"))
      else
        text="\\l[8]"
        for i in 0...RoamingSpecies.length
          poke=RoamingSpecies[i]
          if $game_switches[poke[2]]
            status=$PokemonGlobal.roamPokemon[i]
            if status==true
              if $PokemonGlobal.roamPokemonCaught[i]
                text+=_INTL("{1}（Lv.{2}）已捕获。",
                   PBSpecies.getName(getID(PBSpecies,poke[0])),poke[1])
              else
                text+=_INTL("{1}（Lv.{2}）已击败。",
                   PBSpecies.getName(getID(PBSpecies,poke[0])),poke[1])
              end
            else
              curmap=$PokemonGlobal.roamPosition[i]
              if curmap
                mapinfos=$RPGVX ? load_data("Data/MapInfos.rvdata") : load_data("Data/MapInfos.rxdata")
                text+=_INTL("{1}（Lv.{2}）在地图 {3} 上乱步（{4}）{5}",
                   PBSpecies.getName(getID(PBSpecies,poke[0])),poke[1],curmap,
                   mapinfos[curmap].name,(curmap==$game_map.map_id) ? _INTL("（本地图）") : "")
              else
                text+=_INTL("{1}（Lv.{2}）正在乱步（未设置地图）。",
                   PBSpecies.getName(getID(PBSpecies,poke[0])),poke[1])
              end
            end
          else
            text+=_INTL("{1}（Lv.{2}）未在乱步（开关 {3} 关闭）。",
               PBSpecies.getName(getID(PBSpecies,poke[0])),poke[1],poke[2])
          end
          text+="\n" if i<RoamingSpecies.length-1
        end
        Kernel.pbMessage(text)
      end
    elsif cmd=="roam"
      if RoamingSpecies.length==0
        Kernel.pbMessage(_INTL("没有定义乱步宝可梦。"))
      else
        pbRoamPokemon(true)
        $PokemonGlobal.roamedAlready=false
        Kernel.pbMessage(_INTL("宝可梦已开始乱步。"))
      end
    elsif cmd=="setencounters"
      encdata=load_data("Data/encounters.dat")
      oldencdata=Marshal.dump(encdata)
      mapedited=false
      map=pbDefaultMap()
      loop do
        map=pbListScreen(_INTL("设置遭遇表"),MapLister.new(map))
        break if map<=0
        mapedited=true if map==pbDefaultMap()
        pbEncounterEditorMap(encdata,map)
      end
      save_data(encdata,"Data/encounters.dat")
      pbSaveEncounterData()
      pbClearData()
    elsif cmd=="setmetadata"
      pbMetadataScreen(pbDefaultMap())
      pbClearData()
    elsif cmd=="terraintags"
      pbFadeOutIn(99999) { pbTilesetScreen }
    elsif cmd=="trainertypes"
      pbFadeOutIn(99999) { pbTrainerTypeEditor }
    elsif cmd=="resettrainers"
      if $game_map
        for event in $game_map.events.values
          if event.name[/Trainer\(\d+\)/]
            $game_self_switches[[$game_map.map_id,event.id,"A"]]=false
            $game_self_switches[[$game_map.map_id,event.id,"B"]]=false
          end
        end
        $game_map.need_refresh=true
        Kernel.pbMessage(_INTL("本地图所有训练家已重置。"))
      else
        Kernel.pbMessage(_INTL("这里不能使用这个指令。"))
      end
    elsif cmd=="testwildbattle"
      species=pbChooseSpeciesOrdered(1)
      if species!=0
        params=ChooseNumberParams.new
        params.setRange(1,PBExperience::MAXLEVEL)
        params.setInitialValue(5)
        params.setCancelValue(0)
        level=Kernel.pbMessageChooseNumber(
           _INTL("设置该宝可梦的等级。"),params)
        if level>0
          pbWildBattle(species,level)
        end
      end
    elsif cmd=="testdoublewildbattle"
      Kernel.pbMessage(_INTL("选择第一只宝可梦。"))
      species1=pbChooseSpeciesOrdered(1)
      if species1!=0
        params=ChooseNumberParams.new
        params.setRange(1,PBExperience::MAXLEVEL)
        params.setInitialValue(5)
        params.setCancelValue(0)
        level1=Kernel.pbMessageChooseNumber(
           _INTL("设置第一只宝可梦的等级。"),params)
        if level1>0
          Kernel.pbMessage(_INTL("选择第二只宝可梦。"))
          species2=pbChooseSpeciesOrdered(1)
          if species2!=0
            params=ChooseNumberParams.new
            params.setRange(1,PBExperience::MAXLEVEL)
            params.setInitialValue(5)
            params.setCancelValue(0)
            level2=Kernel.pbMessageChooseNumber(
               _INTL("设置第二只宝可梦的等级。"),params)
            if level2>0
              pbDoubleWildBattle(species1,level1,species2,level2)
            end
          end
        end
      end
    elsif cmd=="testtrainerbattle"
      battle=pbListScreen(_INTL("单打训练家"),TrainerBattleLister.new(0,false))
      if battle
        trainerdata=battle[1]
        pbTrainerBattle(trainerdata[0],trainerdata[1],"...",false,trainerdata[4],true)
      end
    elsif cmd=="testdoubletrainerbattle"
      battle1=pbListScreen(_INTL("双打训练家 1"),TrainerBattleLister.new(0,false))
      if battle1
        battle2=pbListScreen(_INTL("双打训练家 2"),TrainerBattleLister.new(0,false))
        if battle2
          trainerdata1=battle1[1]
          trainerdata2=battle2[1]
          pbDoubleTrainerBattle(trainerdata1[0],trainerdata1[1],trainerdata1[4],"...",
                                trainerdata2[0],trainerdata2[1],trainerdata2[4],"...",
                                true)
        end
      end
    elsif cmd=="relicstone"
      pbRelicStone()
    elsif cmd=="purifychamber"
      pbPurifyChamber()
    elsif cmd=="extracttext"
      pbExtractText
    elsif cmd=="compiletext"
      pbCompileTextUI
    elsif cmd=="compiledata"
      msgwindow=Kernel.pbCreateMessageWindow
      pbCompileAllData(true) {|msg| Kernel.pbMessageDisplay(msgwindow,msg,false) }
      Kernel.pbMessageDisplay(msgwindow,_INTL("全部游戏数据已编译。"))
      Kernel.pbDisposeMessageWindow(msgwindow)
    elsif cmd=="mapconnections"
      pbFadeOutIn(99999) { pbEditorScreen }
    elsif cmd=="animeditor"
      pbFadeOutIn(99999) { pbAnimationEditor }
    elsif cmd=="debugconsole"
      Console::setup_console
    elsif cmd=="togglelogging"
      $INTERNAL=!$INTERNAL
      Kernel.pbMessage(_INTL("战斗调试日志会生成在 Data 文件夹里。")) if $INTERNAL
      Kernel.pbMessage(_INTL("不再生成战斗调试日志。")) if !$INTERNAL
    end
  end
  pbFadeOutAndHide(sprites)
  pbDisposeSpriteHash(sprites)
  viewport.dispose
end



class SpriteWindow_DebugRight < Window_DrawableCommand
  attr_reader :mode

  def initialize
    super(0, 0, Graphics.width, Graphics.height)
  end

  def shadowtext(x,y,w,h,t,align=0)
    width=self.contents.text_size(t).width
    if align==2
      x+=(w-width)
    elsif align==1
      x+=(w/2)-(width/2)
    end
    pbDrawShadowText(self.contents,x,y,[width,w].max,h,t,
       Color.new(12*8,12*8,12*8),Color.new(26*8,26*8,25*8))
  end

  def drawItem(index,count,rect)
    pbSetNarrowFont(self.contents)
    if @mode == 0
      name = $data_system.switches[index+1]
      status = $game_switches[index+1] ? "[ON]" : "[OFF]"
    else
      name = $data_system.variables[index+1]
      status = $game_variables[index+1].to_s
    end
    if name == nil
      name = ''
    end
    id_text = sprintf("%04d:", index+1)
    width = self.contents.text_size(id_text).width
    rect=drawCursor(index,rect)
    totalWidth=rect.width
    idWidth=totalWidth*15/100
    nameWidth=totalWidth*65/100
    statusWidth=totalWidth*20/100
    self.shadowtext(rect.x, rect.y, idWidth, rect.height, id_text)
    self.shadowtext(rect.x+idWidth, rect.y, nameWidth, rect.height, name)
    self.shadowtext(rect.x+idWidth+nameWidth, rect.y, statusWidth, rect.height, status, 2)
  end

  def itemCount
    return (@mode==0) ? $data_system.switches.size-1 : $data_system.variables.size-1
  end

  def mode=(mode)
    @mode = mode
    refresh
  end
end



def pbDebugSetVariable(id,diff)
  pbPlayCursorSE()
  $game_variables[id]=0 if $game_variables[id]==nil
  if $game_variables[id].is_a?(Numeric)
    $game_variables[id]=[$game_variables[id]+diff,99999999].min
    $game_variables[id]=[$game_variables[id],-99999999].max
  end
end

def pbDebugVariableScreen(id)
  value=0
  if $game_variables[id].is_a?(Numeric)
    value=$game_variables[id]
  end
  params=ChooseNumberParams.new
  params.setDefaultValue(value)
  params.setMaxDigits(8)
  params.setNegativesAllowed(true)
  value=Kernel.pbMessageChooseNumber(_INTL("设置变量 {1}。",id),params)
  $game_variables[id]=[value,99999999].min
  $game_variables[id]=[$game_variables[id],-99999999].max
end

def pbDebugScreen(mode)
  viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
  viewport.z=99999
  sprites={}
  sprites["right_window"] = SpriteWindow_DebugRight.new  
  right_window=sprites["right_window"]
  right_window.mode=mode
  right_window.viewport=viewport
  right_window.active=true
  right_window.index=0
  pbFadeInAndShow(sprites)
  loop do
    Graphics.update
    Input.update
    pbUpdateSpriteHash(sprites)
    if Input.trigger?(Input::B)
      pbPlayCancelSE()
      break
    end
    current_id = right_window.index+1
    if mode == 0
      if Input.trigger?(Input::C)
        pbPlayDecisionSE()
        $game_switches[current_id] = (not $game_switches[current_id])
        right_window.refresh
      end
    elsif mode == 1
      if Input.repeat?(Input::RIGHT)
        pbDebugSetVariable(current_id,1)
        right_window.refresh
      elsif Input.repeat?(Input::LEFT)
        pbDebugSetVariable(current_id,-1)
        right_window.refresh
      elsif Input.trigger?(Input::C)
        pbDebugVariableScreen(current_id)
        right_window.refresh
      end
    end
  end
  pbFadeOutAndHide(sprites)
  pbDisposeSpriteHash(sprites)
  viewport.dispose
end



class Scene_Debug
  def main
    Graphics.transition(15)
    pbDebugMenu
    $scene=Scene_Map.new
    $game_map.refresh
    Graphics.freeze
  end
end