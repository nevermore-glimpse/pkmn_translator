module PokemonDebugMixin
  def pbPokemonDebugCommands(settingUpBattle=false)
    commands = CommandMenuList.new
    commands.add("main","hpstatusmenu",_INTL("HP/状态…"))
      commands.add("hpstatusmenu","sethp",_INTL("设置 HP"))
      commands.add("hpstatusmenu","setstatus",_INTL("设置状态"))
      commands.add("hpstatusmenu","fullheal",_INTL("完全恢复"))
      commands.add("hpstatusmenu","makefainted",_INTL("使其濒死"))
      commands.add("hpstatusmenu","setpokerus",_INTL("设置宝可病毒"))

    commands.add("main","levelstats",_INTL("等级/数值…"))
      commands.add("levelstats","setlevel",_INTL("设置等级"))
      commands.add("levelstats","setexp",_INTL("设置经验"))
      commands.add("levelstats","hiddenvalues",_INTL("努力值/个体值/性格值…"))
      commands.add("levelstats","sethappiness",_INTL("设置亲密度"))
      commands.add("levelstats","conteststats",_INTL("华丽大赛数值…"))
        commands.add("conteststats","setbeauty",_INTL("设置美丽"))
        commands.add("conteststats","setcool",_INTL("设置帅气"))
        commands.add("conteststats","setcute",_INTL("设置可爱"))
        commands.add("conteststats","setsmart",_INTL("设置聪明"))
        commands.add("conteststats","settough",_INTL("设置强壮"))
        commands.add("conteststats","setsheen",_INTL("设置光泽"))

    commands.add("main","moves",_INTL("招式…"))
      commands.add("moves","teachmove",_INTL("教授招式"))
      commands.add("moves","forgetmove",_INTL("遗忘招式"))
      commands.add("moves","resetmoves",_INTL("重置招式"))
      commands.add("moves","setmovepp",_INTL("设置招式 PP"))
      commands.add("moves","setinitialmoves",_INTL("重置初始招式"))

    commands.add("main","setability",_INTL("设置特性"))
    commands.add("main","setnature",_INTL("设置性格"))
    commands.add("main","setgender",_INTL("设置性别"))
    commands.add("main","speciesform",_INTL("种类/形态…"))

    commands.add("main","cosmetic",_INTL("外观信息…"))
      commands.add("cosmetic","setshininess",_INTL("设置异色"))
      commands.add("cosmetic","setpokeball",_INTL("设置精灵球"))
      commands.add("cosmetic","setribbons",_INTL("设置奖章"))
      commands.add("cosmetic","setnickname",_INTL("设置昵称"))
      commands.add("cosmetic","ownership",_INTL("持有情况…"))

    commands.add("main","setegg",_INTL("设置蛋"))
    commands.add("main","shadowpkmn",_INTL("暗影宝可梦…"))
    if !settingUpBattle
      commands.add("main","mysterygift",_INTL("神秘礼物"))
      commands.add("main","duplicate",_INTL("复制"))
      commands.add("main","delete",_INTL("删除"))
    end
    return commands
  end

  def pbPokemonDebugActions(command,pkmn,pkmnid,heldpoke=nil,settingUpBattle=false)
    case command
    #===========================================================================
    when "sethp"
      if pkmn.egg?
        pbDisplay(_INTL("{1} 是蛋。",pkmn.name))
      else
        params = ChooseNumberParams.new
        params.setRange(0,pkmn.totalhp)
        params.setDefaultValue(pkmn.hp)
        newhp = pbMessageChooseNumber(
           _INTL("设置 {1} 的 HP（最大 {2}）。",pkmn.name,pkmn.totalhp),params) { pbUpdate }
        if newhp!=pkmn.hp
          pkmn.hp = newhp
          pbRefreshSingle(pkmnid)
        end
      end
    #===========================================================================
    when "setstatus"
      if pkmn.egg?
        pbDisplay(_INTL("{1} 是蛋。",pkmn.name))
      elsif pkmn.hp<=0
        pbDisplay(_INTL("{1} 已濒死，无法修改状态。",pkmn.name))
      else
        cmd = 0
        loop do
          cmd = pbShowCommands(_INTL("设置 {1} 的状态。",pkmn.name),[
             _INTL("【治愈】"),
             _INTL("睡眠"),
             _INTL("中毒"),
             _INTL("灼伤"),
             _INTL("麻痹"),
             _INTL("冰冻")
          ],cmd)
          break if cmd<0
          case cmd
          when 0   # Cure
            pkmn.healStatus
            pbDisplay(_INTL("{1} 的状态已治愈。",pkmn.name))
            pbRefreshSingle(pkmnid)
          else   # Give status problem
            count = 0
            cancel = false
            if cmd==PBStatuses::SLEEP
              params = ChooseNumberParams.new
              params.setRange(0,9)
              params.setDefaultValue(3)
              count = pbMessageChooseNumber(
                 _INTL("设置该宝可梦的睡眠回合数。"),params) { pbUpdate }
              cancel = true if count<=0
            end
            if !cancel
              pkmn.status      = cmd
              pkmn.statusCount = count
              pbRefreshSingle(pkmnid)
            end
          end
        end
      end
    #===========================================================================
    when "fullheal"
      if pkmn.egg?
        pbDisplay(_INTL("{1} 是蛋。",pkmn.name))
      else
        pkmn.heal
        pbDisplay(_INTL("{1} 已完全治愈。",pkmn.name))
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "makefainted"
      if pkmn.egg?
        pbDisplay(_INTL("{1} 是蛋。",pkmn.name))
      else
        pkmn.hp = 0
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "setpokerus"
      cmd = 0
      loop do
        pokerus = (pkmn.pokerus) ? pkmn.pokerus : 0
        msg = [_INTL("{1} 没有宝可病毒。",pkmn.name),
               _INTL("携带病毒株 {1}，还可传染 {2} 天。",pokerus/16,pokerus%16),
               _INTL("携带病毒株 {1}，已无传染性。",pokerus/16)][pkmn.pokerusStage]
        cmd = pbShowCommands(msg,[
           _INTL("给予随机血脉"),
           _INTL("设为不会感染波动"),
           _INTL("治愈波动")],cmd)
        break if cmd<0
        case cmd
        when 0   # Give random strain
          pkmn.givePokerus
          pbRefreshSingle(pkmnid)
        when 1   # Make not infectious
          if pokerus>0
            strain = pokerus/16
            p = strain << 4
            pkmn.pokerus = p
            pbRefreshSingle(pkmnid)
          end
        when 2   # Clear Pokérus
          pkmn.pokerus = 0
          pbRefreshSingle(pkmnid)
        end
      end
    #===========================================================================
    when "setlevel"
      if pkmn.egg?
        pbDisplay(_INTL("{1} 是蛋。",pkmn.name))
      else
        mLevel = PBExperience.maxLevel
        params = ChooseNumberParams.new
        params.setRange(1,mLevel)
        params.setDefaultValue(pkmn.level)
        level = pbMessageChooseNumber(
           _INTL("设置宝可梦的等级（最大 {1}）。",mLevel),params) { pbUpdate }
        if level!=pkmn.level
          pkmn.level = level
          pkmn.calcStats
          pbRefreshSingle(pkmnid)
        end
      end
    #===========================================================================
    when "setexp"
      if pkmn.egg?
        pbDisplay(_INTL("{1} 是蛋。",pkmn.name))
      else
        minxp = PBExperience.pbGetStartExperience(pkmn.level,pkmn.growthrate)
        maxxp = PBExperience.pbGetStartExperience(pkmn.level+1,pkmn.growthrate)
        if minxp==maxxp
          pbDisplay(_INTL("{1} 已到最高等级。",pkmn.name))
        else
          params = ChooseNumberParams.new
          params.setRange(minxp,maxxp-1)
          params.setDefaultValue(pkmn.exp)
          newexp = pbMessageChooseNumber(
             _INTL("设置宝可梦的经验值（范围 {1}-{2}）。",minxp,maxxp-1),params) { pbUpdate }
          if newexp!=pkmn.exp
            pkmn.exp = newexp
            pkmn.calcStats
            pbRefreshSingle(pkmnid)
          end
        end
      end
    #===========================================================================
    when "hiddenvalues"
      numstats = 6
      cmd = 0
      loop do
        persid = sprintf("0x%08X",pkmn.personalID)
        cmd = pbShowCommands(_INTL("个人 ID 为 {1}。",persid),[
             _INTL("设置努力值"),
             _INTL("设置个体值"),
             _INTL("随机 pID")],cmd)
        break if cmd<0
        case cmd
        when 0   # Set EVs
          cmd2 = 0
          loop do
            totalev = 0
            evcommands = []
            for i in 0...numstats
              evcommands.push(PBStats.getName(i)+" (#{pkmn.ev[i]})")
              totalev += pkmn.ev[i]
            end
            evcommands.push(_INTL("全部随机"))
            evcommands.push(_INTL("全部随机到最大"))
            cmd2 = pbShowCommands(_INTL("要修改哪项 EV？\n总计：{1}/{2}（{3}%）",
               totalev,PokeBattle_Pokemon::EV_LIMIT,
               100*totalev/PokeBattle_Pokemon::EV_LIMIT),evcommands,cmd2)
            break if cmd2<0
            if cmd2<numstats
              params = ChooseNumberParams.new
              upperLimit = 0
              for i in 0...numstats
                upperLimit += pkmn.ev[i] if i!=cmd2
              end
              upperLimit = PokeBattle_Pokemon::EV_LIMIT-upperLimit
              upperLimit = [upperLimit,PokeBattle_Pokemon::EV_STAT_LIMIT].min
              thisValue = [pkmn.ev[cmd2],upperLimit].min
              params.setRange(0,upperLimit)
              params.setDefaultValue(thisValue)
              params.setCancelValue(thisValue)
              f = pbMessageChooseNumber(_INTL("设置 {1} 的 EV（最大 {2}）。",
                 PBStats.getName(cmd2),upperLimit),params) { pbUpdate }
              if f!=pkmn.ev[cmd2]
                pkmn.ev[cmd2] = f
                pkmn.calcStats
                pbRefreshSingle(pkmnid)
              end
            elsif cmd2<evcommands.length   # Randomise
              evTotalTarget = PokeBattle_Pokemon::EV_LIMIT
              if cmd2==evcommands.length-2
                evTotalTarget = rand(PokeBattle_Pokemon::EV_LIMIT)
              end
              for i in 0...numstats
                pkmn.ev[i] = 0
              end
              while evTotalTarget>0
                r = rand(numstats)
                next if pkmn.ev[r]>=PokeBattle_Pokemon::EV_STAT_LIMIT
                addVal = 1+rand(PokeBattle_Pokemon::EV_STAT_LIMIT/4)
                addVal = evTotalTarget if addVal>evTotalTarget
                addVal = [addVal,PokeBattle_Pokemon::EV_STAT_LIMIT-pkmn.ev[r]].min
                next if addVal==0
                pkmn.ev[r] += addVal
                evTotalTarget -= addVal
              end
              pkmn.calcStats
              pbRefreshSingle(pkmnid)
            end
          end
        when 1   # Set IVs
          cmd2 = 0
          loop do
            hiddenpower = pbHiddenPower(pkmn)
            totaliv = 0
            ivcommands = []
            for i in 0...numstats
              ivcommands.push(PBStats.getName(i)+" (#{pkmn.iv[i]})")
              totaliv += pkmn.iv[i]
            end
            msg = _INTL("要修改哪项 IV？\n觉醒力量：\n{1}，威力 {2}\n总计：{3}/{4}（{5}%）",
               PBTypes.getName(hiddenpower[0]),hiddenpower[1],totaliv,numstats*31,
               100*totaliv/(numstats*31))
            ivcommands.push(_INTL("全部随机"))
            cmd2 = pbShowCommands(msg,ivcommands,cmd2)
            break if cmd2<0
            if cmd2<numstats
              params = ChooseNumberParams.new
              params.setRange(0,31)
              params.setDefaultValue(pkmn.iv[cmd2])
              params.setCancelValue(pkmn.iv[cmd2])
              f = pbMessageChooseNumber(_INTL("设置 {1} 的 IV（最大 31）。",
                 PBStats.getName(cmd2)),params) { pbUpdate }
              if f!=pkmn.iv[cmd2]
                pkmn.iv[cmd2] = f
                pkmn.calcStats
                pbRefreshSingle(pkmnid)
              end
            elsif cmd2==ivcommands.length-1   # Randomise
              for i in 0...numstats
                pkmn.iv[i] = rand(PokeBattle_Pokemon::IV_STAT_LIMIT+1)
              end
              pkmn.calcStats
              pbRefreshSingle(pkmnid)
            end
          end
        when 2   # Randomise pID
          pkmn.personalID = rand(256)
          pkmn.personalID |= rand(256)<<8
          pkmn.personalID |= rand(256)<<16
          pkmn.personalID |= rand(256)<<24
          pkmn.calcStats
          pbRefreshSingle(pkmnid)
        end
      end
    #===========================================================================
    when "sethappiness"
      params = ChooseNumberParams.new
      params.setRange(0,255)
      params.setDefaultValue(pkmn.happiness)
      h = pbMessageChooseNumber(
         _INTL("设置该宝可梦的亲密度（最高 255）。"),params) { pbUpdate }
      if h!=pkmn.happiness
        pkmn.happiness = h
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "setbeauty", "setcool", "setcute", "setsmart", "settough", "setsheen"
      case command
      when "setbeauty"; statname = _INTL("美丽"); defval = pkmn.beauty
      when "setcool";   statname = _INTL("酷");   defval = pkmn.cool
      when "setcute";   statname = _INTL("可爱");   defval = pkmn.cute
      when "setsmart";  statname = _INTL("聪明");  defval = pkmn.smart
      when "settough";  statname = _INTL("健壮");  defval = pkmn.tough
      when "setsheen";  statname = _INTL("光泽");  defval = pkmn.sheen
      end
      params = ChooseNumberParams.new
      params.setRange(0,255)
      params.setDefaultValue(defval)
      newval = pbMessageChooseNumber(
         _INTL("设置宝可梦的 {1}（最大 255）。",statname),params) { pbUpdate }
      if newval!=defval
        case command
        when "setbeauty"; pkmn.beauty = newval
        when "setcool";   pkmn.cool   = newval
        when "setcute";   pkmn.cute   = newval
        when "setsmart";  pkmn.smart  = newval
        when "settough";  pkmn.tough  = newval
        when "setsheen";  pkmn.sheen  = newval
        end
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "teachmove"
      move = pbChooseMoveList
      if move!=0
        pbLearnMove(pkmn,move)
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "forgetmove"
      moveindex = pbChooseMove(pkmn,_INTL("选择要忘记的招式。"))
      if moveindex>=0
        movename = PBMoves.getName(pkmn.moves[moveindex].id)
        pkmn.pbDeleteMoveAtIndex(moveindex)
        pbDisplay(_INTL("{1} 忘记了 {2}。",pkmn.name,movename))
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "resetmoves"
      pkmn.resetMoves
      pbDisplay(_INTL("{1} 的招式已重置。",pkmn.name))
      pbRefreshSingle(pkmnid)
    #===========================================================================
    when "setmovepp"
      cmd = 0
      loop do
        commands = []
        for i in pkmn.moves
          break if i.id==0
          if i.totalpp<=0
            commands.push(_INTL("{1}（PP：---）",PBMoves.getName(i.id)))
          else
            commands.push(_INTL("{1}（PP：{2}/{3}）",PBMoves.getName(i.id),i.pp,i.totalpp))
          end
        end
        commands.push(_INTL("恢复全部PP"))
        cmd = pbShowCommands(_INTL("要修改哪个招式的PP？"),commands,cmd)
        break if cmd<0
        if cmd>=0 && cmd<commands.length-1   # Move
          move = pkmn.moves[cmd]
          movename = PBMoves.getName(move.id)
          if move.totalpp<=0
            pbDisplay(_INTL("{1} 的 PP 无限。",movename))
          else
            cmd2 = 0
            loop do
              msg = _INTL("{1}：PP {2}/{3}（PP 提升 {4}/3）",movename,move.pp,move.totalpp,move.ppup)
              cmd2 = pbShowCommands(msg,[
                 _INTL("设置PP"),
                 _INTL("PP全满"),
                 _INTL("设置PP上限")],cmd2)
              break if cmd2<0
              case cmd2
              when 0   # Change PP
                params = ChooseNumberParams.new
                params.setRange(0,move.totalpp)
                params.setDefaultValue(move.pp)
                h = pbMessageChooseNumber(
                   _INTL("设置 {1} 的 PP（最大 {2}）。",movename,move.totalpp),params) { pbUpdate }
                move.pp = h
              when 1   # Full PP
                move.pp = move.totalpp
              when 2   # Change PP Up
                params = ChooseNumberParams.new
                params.setRange(0,3)
                params.setDefaultValue(move.ppup)
                h = pbMessageChooseNumber(
                   _INTL("设置 {1} 的 PP 提升（最大 3）。",movename),params) { pbUpdate }
                move.ppup = h
                move.pp = move.totalpp if move.pp>move.totalpp
              end
            end
          end
        elsif cmd==commands.length-1   # Restore all PP
          pkmn.healPP
        end
      end
    #===========================================================================
    when "setinitialmoves"
      pkmn.pbRecordFirstMoves
      pbDisplay(_INTL("{1} 的招式已设为其最初学会的招式。",pkmn.name))
      pbRefreshSingle(pkmnid)
    #===========================================================================
    when "setability"
      cmd = 0
      loop do
        abils = pkmn.getAbilityList
        oldabil = PBAbilities.getName(pkmn.ability)
        commands = []
        for i in abils
          commands.push(((i[1]<2) ? "" : "(H) ")+PBAbilities.getName(i[0]))
        end
        commands.push(_INTL("移除覆盖"))
        msg = [_INTL("特性 {1} 是自然获得的。",oldabil),
               _INTL("特性 {1} 已被强制指定。",oldabil)][pkmn.abilityflag!=nil ? 1 : 0]
        cmd = pbShowCommands(msg,commands,cmd)
        break if cmd<0
        if cmd>=0 && cmd<abils.length   # Set ability override
          pkmn.setAbility(abils[cmd][1])
        elsif cmd==abils.length   # Remove override
          pkmn.abilityflag = nil
        end
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "setnature"
      commands = []
      (PBNatures.getCount).times do |i|
        statUp   = PBNatures.getStatRaised(i)
        statDown = PBNatures.getStatLowered(i)
        if statUp!=statDown
          text = _INTL("{1}（+{2}，-{3}）",PBNatures.getName(i),
             PBStats.getNameBrief(statUp),PBStats.getNameBrief(statDown))
        else
          text = _INTL("{1}（---）",PBNatures.getName(i))
        end
        commands.push(text)
      end
      commands.push(_INTL("【移除覆盖】"))
      cmd = pkmn.nature
      loop do
        oldnature = PBNatures.getName(pkmn.nature)
        msg = [_INTL("性格 {1} 是自然获得的。",oldnature),
               _INTL("性格 {1} 已被强制指定。",oldnature)][pkmn.natureflag ? 1 : 0]
        cmd = pbShowCommands(msg,commands,cmd)
        break if cmd<0
        if cmd>=0 && cmd<PBNatures.getCount   # Set nature override
          pkmn.setNature(cmd)
          pkmn.calcStats
        elsif cmd==PBNatures.getCount   # Remove override
          pkmn.natureflag = nil
        end
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "setgender"
      if pkmn.singleGendered?
        pbDisplay(_INTL("{1} 是单性别或无性别。",pkmn.speciesName))
      else
        cmd = 0
        loop do
          oldgender = (pkmn.male?) ? _INTL("雄性") : _INTL("雌性")
          msg = [_INTL("性别 {1} 是自然获得的。",oldgender),
               _INTL("性别 {1} 已被强制指定。",oldgender)][pkmn.genderflag ? 1 : 0]
          cmd = pbShowCommands(msg,[
             _INTL("设为男性"),
             _INTL("设为女性"),
             _INTL("移除覆盖")],cmd)
          break if cmd<0
          case cmd
          when 0   # Make male
            pkmn.makeMale
            if !pkmn.male?
              pbDisplay(_INTL("{1} 的性别无法修改。",pkmn.name))
            end
          when 1   # Make female
            pkmn.makeFemale
            if !pkmn.female?
              pbDisplay(_INTL("{1} 的性别无法修改。",pkmn.name))
            end
          when 2   # Remove override
            pkmn.genderflag = nil
          end
          pbSeenForm(pkmn) if !settingUpBattle
          pbRefreshSingle(pkmnid)
        end
      end
    #===========================================================================
    when "speciesform"
      cmd = 0
      loop do
        msg = [_INTL("种类 {1}，形态 {2}。",pkmn.speciesName,pkmn.form),
               _INTL("种类 {1}，形态 {2}（已强制）。",pkmn.speciesName,pkmn.form)][(pkmn.forcedForm!=nil) ? 1 : 0]
        cmd = pbShowCommands(msg,[
           _INTL("设置种类"),
           _INTL("设置形态"),
           _INTL("移除覆盖")],cmd)
        break if cmd<0
        case cmd
        when 0   # Set species
          species = pbChooseSpeciesList(pkmn.species)
          if species!=0 && species!=pkmn.species
            pkmn.species = species
            pkmn.calcStats
            pbSeenForm(pkmn) if !settingUpBattle
            pbRefreshSingle(pkmnid)
          end
        when 1   # Set form
          cmd2 = 0
          formcmds = [[],[]]
          formdata = pbLoadFormToSpecies
          formdata[pkmn.species] = [pkmn.species] if !formdata[pkmn.species]
          for form in 0...formdata[pkmn.species].length
            fSpecies = pbGetFSpeciesFromForm(pkmn.species,form)
            formname = pbGetMessage(MessageTypes::FormNames,fSpecies)
            formname = _INTL("未命名形态") if !formname || formname==""
            formname = _INTL("{1}：{2}",form,formname)
            formcmds[0].push(form); formcmds[1].push(formname)
            cmd2 = form if pkmn.form==form
          end
          if formcmds[0].length<=1
            pbDisplay(_INTL("种类 {1} 只有一个形态。",pkmn.speciesName))
          else
            cmd2 = pbShowCommands(_INTL("设置该宝可梦的形态。"),formcmds[1],cmd2)
            next if cmd2<0
            f = formcmds[0][cmd2]
            if f!=pkmn.form
              if MultipleForms.hasFunction?(pkmn,"getForm")
                next if !pbConfirm(_INTL("该种类自行决定形态，要覆盖吗？"))
                pkmn.forcedForm = f
              end
              pkmn.form = f
              pbSeenForm(pkmn) if !settingUpBattle
              pbRefreshSingle(pkmnid)
            end
          end
        when 2   # Remove override
          pkmn.forcedForm = nil
          pbRefreshSingle(pkmnid)
        end
      end
    #===========================================================================
    when "setshininess"
      cmd = 0
      loop do
        oldshiny = (pkmn.shiny?) ? _INTL("闪光") : _INTL("普通")
        msg = [_INTL("闪光（{1}）是自然获得的。",oldshiny),
               _INTL("闪光（{1}）已被强制指定。",oldshiny)][pkmn.shinyflag!=nil ? 1 : 0]
        cmd = pbShowCommands(msg,[
             _INTL("设为闪光"),
             _INTL("设为普通（无闪光）"),
             _INTL("移除覆盖")],cmd)
        break if cmd<0
        case cmd
        when 0   # Make shiny
          pkmn.makeShiny
        when 1   # Make normal
          pkmn.makeNotShiny
        when 2   # Remove override
          pkmn.shinyflag = nil
        end
        pbRefreshSingle(pkmnid)
      end
    #===========================================================================
    when "setnickname"
      cmd = 0
      loop do
        speciesname = PBSpecies.getName(pkmn.species)
        msg = [_INTL("{1} 的昵称是 {2}。",speciesname,pkmn.name),
               _INTL("{1} 没有昵称。",speciesname)][pkmn.name==speciesname ? 1 : 0]
        cmd = pbShowCommands(msg,[
             _INTL("重命名"),
             _INTL("清除名字")],cmd)
        break if cmd<0
        case cmd
        when 0   # Rename
          oldname = (pkmn.name && pkmn.name!=speciesname) ? pkmn.name : ""
          newname = pbEnterPokemonName(_INTL("{1} 的昵称？",speciesname),
             0,PokeBattle_Pokemon::MAX_POKEMON_NAME_SIZE,oldname,pkmn)
          if newname && newname!=""
            pkmn.name = newname
            pbRefreshSingle(pkmnid)
          end
        when 1   # Erase name
          pkmn.name = speciesname
          pbRefreshSingle(pkmnid)
        end
      end
    #===========================================================================
    when "setpokeball"
      commands = []; balls = []
      for key in $BallTypes.keys
        item = getID(PBItems,$BallTypes[key])
        balls.push([key.to_i,PBItems.getName(item)]) if item && item>0
      end
      balls.sort! { |a,b| a[1]<=>b[1] }
      cmd = 0
      for i in 0...balls.length
        if balls[i][0]==pkmn.ballused
          cmd = i; break
        end
      end
      for i in balls
        commands.push(i[1])
      end
      loop do
        oldball = PBItems.getName(pbBallTypeToItem(pkmn.ballused))
        cmd = pbShowCommands(_INTL("使用了 {1}。",oldball),commands,cmd)
        break if cmd<0
        pkmn.ballused = balls[cmd][0]
      end
    #===========================================================================
    when "setribbons"
      cmd = 0
      loop do
        commands = []
        for i in 1..PBRibbons.maxValue
          commands.push(_INTL("{1} {2}",
             (pkmn.hasRibbon?(i)) ? "[Y]" : "[  ]",PBRibbons.getName(i)))
        end
        commands.push(_INTL("全部给予"))
        commands.push(_INTL("全部清除"))
        cmd = pbShowCommands(_INTL("{1} 枚奖章。",pkmn.ribbonCount),commands,cmd)
        break if cmd<0
        if cmd>=0 && cmd<PBRibbons.maxValue   # Toggle ribbon
          if pkmn.hasRibbon?(cmd+1)
            pkmn.takeRibbon(cmd+1)
          else
            pkmn.giveRibbon(cmd+1)
          end
        elsif cmd==commands.length-2   # Give all
          for i in 1..PBRibbons.maxValue
            pkmn.giveRibbon(i)
          end
        elsif cmd==commands.length-1   # Clear all
          for i in 1..PBRibbons.maxValue
            pkmn.takeRibbon(i)
          end
        end
      end
    #===========================================================================
    when "ownership"
      cmd = 0
      loop do
        gender = [_INTL("男性"),_INTL("女性"),_INTL("未知")][pkmn.otgender]
        msg = [_INTL("玩家的宝可梦\n{1}\n{2}\n{3}（{4}）",pkmn.ot,gender,pkmn.publicID,pkmn.trainerID),
               _INTL("外来宝可梦\n{1}\n{2}\n{3}（{4}）",pkmn.ot,gender,pkmn.publicID,pkmn.trainerID)
              ][pkmn.foreign?($Trainer) ? 1 : 0]
        cmd = pbShowCommands(msg,[
             _INTL("设为玩家所有"),
             _INTL("设置初训家的名字"),
             _INTL("设置初训家的性别"),
             _INTL("随机信赖ID"),
             _INTL("设置信赖ID")],cmd)
        break if cmd<0
        case cmd
        when 0   # Make player's
          pkmn.trainerID = $Trainer.id
          pkmn.ot        = $Trainer.name
          pkmn.otgender  = $Trainer.gender
        when 1   # Set OT's name
          pkmn.ot = pbEnterPlayerName(_INTL("{1} 的初训家名字？",pkmn.name),1,MAX_PLAYER_NAME_SIZE)
        when 2   # Set OT's gender
          cmd2 = pbShowCommands(_INTL("设置初训家的性别。"),
             [_INTL("男性"),_INTL("女性"),_INTL("未知")],pkmn.otgender)
          pkmn.otgender = cmd2 if cmd2>=0
        when 3   # Random foreign ID
          pkmn.trainerID = $Trainer.getForeignID
        when 4   # Set foreign ID
          params = ChooseNumberParams.new
          params.setRange(0,65535)
          params.setDefaultValue(pkmn.publicID)
          val = pbMessageChooseNumber(
             _INTL("设置新ID（最高 65535）。"),params) { pbUpdate }
          pkmn.trainerID = val
          pkmn.trainerID |= val << 16
        end
      end
    #===========================================================================
    when "setegg"
      cmd = 0
      loop do
        msg = [_INTL("不是蛋"),
               _INTL("蛋步数：{1}。",pkmn.eggsteps)][pkmn.egg? ? 1 : 0]
        cmd = pbShowCommands(msg,[
             _INTL("生成蛋"),
             _INTL("生成宝可梦"),
             _INTL("把剩余孵化步数设为 1")],cmd)
        break if cmd<0
        case cmd
        when 0   # Make egg
          if !pkmn.egg? && (pbHasEgg?(pkmn.species) ||
             pbConfirm(_INTL("{1} 变成蛋不合法。仍要设为蛋吗？",PBSpecies.getName(pkmn.species))))
            pkmn.level = EGG_LEVEL
            pkmn.calcStats
            pkmn.name = _INTL("蛋")
            pkmn.eggsteps = pbGetSpeciesData(pkmn.species,pkmn.form,SpeciesStepsToHatch)
            pkmn.hatchedMap = 0
            pkmn.obtainMode = 1
            pbRefreshSingle(pkmnid)
          end
        when 1   # Make Pokémon
          if pkmn.egg?
            pkmn.name       = PBSpecies.getName(pkmn.species)
            pkmn.eggsteps   = 0
            pkmn.hatchedMap = 0
            pkmn.obtainMode = 0
            pbRefreshSingle(pkmnid)
          end
        when 2   # Set eggsteps to 1
          pkmn.eggsteps = 1 if pkmn.egg?
        end
      end
    #===========================================================================
    when "shadowpkmn"
      cmd = 0
      loop do
        msg = [_INTL("不是暗影宝可梦。"),
               _INTL("心灵槽为 {1}（阶段 {2}）。",pkmn.heartgauge,pkmn.heartStage)
              ][pkmn.shadowPokemon? ? 1 : 0]
        cmd = pbShowCommands(msg,[
           _INTL("生成暗影宝可梦"),
           _INTL("设置心之刻度")],cmd)
        break if cmd<0
        case cmd
        when 0   # Make Shadow
          if !pkmn.shadowPokemon?
            pkmn.makeShadow
            pbRefreshSingle(pkmnid)
          else
            pbDisplay(_INTL("{1} 已经是黑暗宝可梦。",pkmn.name))
          end
        when 1   # Set heart gauge
          if pkmn.shadowPokemon?
            oldheart = pkmn.heartgauge
            params = ChooseNumberParams.new
            params.setRange(0,PokeBattle_Pokemon::HEARTGAUGESIZE)
            params.setDefaultValue(pkmn.heartgauge)
            val = pbMessageChooseNumber(
               _INTL("设置心灵槽（最大 {1}）。",PokeBattle_Pokemon::HEARTGAUGESIZE),
               params) { pbUpdate }
            if val!=oldheart
              pkmn.adjustHeart(val-oldheart)
              pbReadyToPurify(pkmn)
            end
          else
            pbDisplay(_INTL("{1} 不是黑暗宝可梦。",pkmn.name))
          end
        end
      end
    #===========================================================================
    when "mysterygift"
      pbCreateMysteryGift(0,pkmn)
    #===========================================================================
    when "duplicate"
      if pbConfirm(_INTL("确定要复制这只宝可梦吗？"))
        clonedpkmn = pkmn.clone
        if self.is_a?(PokemonPartyScreen)
          pbStorePokemon(clonedpkmn)
          pbHardRefresh
          pbDisplay(_INTL("该宝可梦已复制。"))
        elsif self.is_a?(PokemonStorageScreen)
          if @storage.pbMoveCaughtToParty(clonedpkmn)
            if pkmnid[0]!=-1
              pbDisplay(_INTL("复制的宝可梦已放进你的队伍。"))
            end
          else
            oldbox = @storage.currentBox
            newbox = @storage.pbStoreCaught(clonedpkmn)
            if newbox<0
              pbDisplay(_INTL("所有仓库格子都已满。"))
            elsif newbox!=oldbox
              pbDisplay(_INTL("重复的宝可梦已移到「{1}」仓库。",@storage[newbox].name))
              @storage.currentBox = oldbox
            end
          end
          pbHardRefresh
        end
        return false
      end
    #===========================================================================
    when "delete"
      if pbConfirm(_INTL("确定要删除这只宝可梦吗？"))
        if self.is_a?(PokemonPartyScreen)
          @party[pkmnid] = nil
          @party.compact!
          pbHardRefresh
        elsif self.is_a?(PokemonStorageScreen)
          @scene.pbRelease(pkmnid,heldpoke)
          (heldpoke) ? @heldpkmn = nil : @storage.pbDelete(pkmnid[0],pkmnid[1])
          @scene.pbRefresh
        end
        return false
      end
    end
    return true
  end

  def pbPokemonDebug(pkmn,pkmnid,heldpoke=nil,settingUpBattle=false)
    command = 0
    commands = pbPokemonDebugCommands(settingUpBattle)
    loop do
      command = pbShowCommands(_INTL("要对 {1} 做什么？",pkmn.name),commands.list,command)
      if command<0
        parent = commands.getParent
        if parent
          commands.currentList = parent[0]
          command = parent[1]
        else
          break
        end
      else
        cmd = commands.getCommand(command)
        if commands.hasSubMenu?(cmd)
          commands.currentList = cmd
          command = 0
        else
          cont = pbPokemonDebugActions(cmd,pkmn,pkmnid,heldpoke,settingUpBattle)
          break if !cont
        end
      end
    end
  end
end



class PokemonPartyScreen
  include PokemonDebugMixin
end



class PokemonStorageScreen
  include PokemonDebugMixin
end



class PokemonDebugPartyScreen
  include PokemonDebugMixin
end
