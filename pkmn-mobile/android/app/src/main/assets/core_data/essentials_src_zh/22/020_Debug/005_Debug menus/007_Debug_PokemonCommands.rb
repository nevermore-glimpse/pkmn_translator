#===============================================================================
# HP/Status options.
#===============================================================================

MenuHandlers.add(:pokemon_debug_menu, :hp_status_menu, {
  "name"   => _INTL("HP/状态…"),
  "parent" => :main
})

MenuHandlers.add(:pokemon_debug_menu, :set_hp, {
  "name"   => _INTL("设置 HP"),
  "parent" => :hp_status_menu,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    if pkmn.egg?
      screen.show_message(_INTL("{1} 是蛋。", pkmn.name))
      next false
    end
    params = ChooseNumberParams.new
    params.setRange(0, pkmn.totalhp)
    params.setDefaultValue(pkmn.hp)
    new_hp = screen.choose_number("\\se[]" + _INTL("设置宝可梦的 HP（最大 {1}）。", params.maxNumber), params)
    if new_hp != pkmn.hp
      pkmn.hp = new_hp
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_status, {
  "name"   => _INTL("设置状态"),
  "parent" => :hp_status_menu,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    if pkmn.egg?
      screen.show_message(_INTL("{1} 是蛋。", pkmn.name))
      next false
    elsif pkmn.hp <= 0
      screen.show_message(_INTL("{1} 已濒死，无法修改状态。", pkmn.name))
      next false
    end
    commands = {:NONE => _INTL("【治愈】")}
    GameData::Status.each do |s|
      commands[s.id] = _INTL("设置 {1}", s.name) if s.id != :NONE
    end
    cmd = commands.keys.first
    loop do
      msg = _INTL("当前状态：{1}", GameData::Status.get(pkmn.status).name)
      if pkmn.status == :SLEEP
        msg = _INTL("当前状态：{1}（回合：{2}）", GameData::Status.get(pkmn.status).name, pkmn.statusCount)
      end
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :NONE   # Cure
        pkmn.heal_status
        screen.refresh
      else   # Give status problem
        count = 0
        cancel = false
        if cmd == :SLEEP
          params = ChooseNumberParams.new
          params.setRange(0, 9)
          params.setDefaultValue(3)
          count = screen.choose_number("\\se[]" + _INTL("设置该宝可梦的睡眠回合数。"), params)
          cancel = true if count <= 0
        end
        if !cancel
          pkmn.status      = cmd
          pkmn.statusCount = count
          screen.refresh
        end
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :full_heal, {
  "name"   => _INTL("完全恢复"),
  "parent" => :hp_status_menu,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    if pkmn.egg?
      screen.show_message(_INTL("{1} 是蛋。", pkmn.name))
    else
      pkmn.heal
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :make_fainted, {
  "name"   => _INTL("使其濒死"),
  "parent" => :hp_status_menu,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    if pkmn.egg?
      screen.show_message(_INTL("{1} 是蛋。", pkmn.name))
    else
      pkmn.hp = 0
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_pokerus, {
  "name"   => _INTL("设置宝可病毒"),
  "parent" => :hp_status_menu,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :random_strain  => _INTL("给予随机血脉"),
      :non_infectious => _INTL("设为不会感染波动"),
      :clear          => _INTL("治愈波动")
    }
    cmd = commands.keys.first
    loop do
      pokerus = (pkmn.pokerus) ? pkmn.pokerus : 0
      msg = [_INTL("{1} 没有宝可病毒。", pkmn.name),
             _INTL("携带病毒株 {1}，还可传染 {2} 天。", pokerus / 16, pokerus % 16),
             _INTL("携带病毒株 {1}，已无传染性。", pokerus / 16)][pkmn.pokerusStage]
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :random_strain
        pkmn.pokerus = 0
        pkmn.givePokerus
        screen.refresh
      when :non_infectious
        if pokerus > 0
          strain = pokerus / 16
          p = strain << 4
          pkmn.pokerus = p
          screen.refresh
        end
      when :clear
        pkmn.pokerus = 0
        screen.refresh
      end
    end
    next false
  }
})

#===============================================================================
# Level/stats options.
#===============================================================================

MenuHandlers.add(:pokemon_debug_menu, :level_stats, {
  "name"   => _INTL("等级/数值…"),
  "parent" => :main
})

MenuHandlers.add(:pokemon_debug_menu, :set_level, {
  "name"   => _INTL("设置等级"),
  "parent" => :level_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    if pkmn.egg?
      screen.show_message(_INTL("{1} 是蛋。", pkmn.name))
      next false
    end
    params = ChooseNumberParams.new
    params.setRange(1, GameData::GrowthRate.max_level)
    params.setDefaultValue(pkmn.level)
    level = screen.choose_number("\\se[]" + _INTL("设置宝可梦的等级（最大 {1}）。", params.maxNumber), params)
    if level != pkmn.level
      pkmn.level = level
      pkmn.calc_stats
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_exp, {
  "name"   => _INTL("设置经验"),
  "parent" => :level_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    if pkmn.egg?
      screen.show_message(_INTL("{1} 是蛋。", pkmn.name))
      next false
    end
    min_xp = pkmn.growth_rate.minimum_exp_for_level(pkmn.level)
    max_xp = pkmn.growth_rate.minimum_exp_for_level(pkmn.level + 1)
    if min_xp == max_xp
      screen.show_message(_INTL("{1} 已到最高等级。", pkmn.name))
      next false
    end
    params = ChooseNumberParams.new
    params.setRange(min_xp, max_xp - 1)
    params.setDefaultValue(pkmn.exp)
    new_exp = screen.choose_number("\\se[]" + _INTL("设置宝可梦的经验值（范围 {1}-{2}）。", min_xp, max_xp - 1), params)
    if new_exp != pkmn.exp
      pkmn.exp = new_exp
      pkmn.calc_stats
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :hidden_values, {
  "name"   => _INTL("努力值/个体值/性格值…"),
  "parent" => :level_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :set_evs    => _INTL("设置努力值"),
      :set_ivs    => _INTL("设置个体值"),
      :random_pid => _INTL("随机化 pID")
    }
    cmd = commands.keys.first
    loop do
      pers_id = sprintf("0x%08X", pkmn.personalID)
      cmd = screen.show_menu(_INTL("个人 ID 为 {1}。", pers_id), commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :set_evs
        ev_cmd = nil
        loop do
          total_evs = 0
          ev_commands = {}
          stats = []
          GameData::Stat.each_main do |s|
            ev_commands[s.id] = s.name + " (#{pkmn.ev[s.id]})"
            stats.push(s.id)
            total_evs += pkmn.ev[s.id]
          end
          ev_commands[:randomize] = _INTL("全部随机化")
          ev_commands[:max_randomize] = _INTL("全部最大随机化")
          ev_cmd ||= ev_commands.keys.first
          ev_cmd = screen.show_menu(
            _INTL("要修改哪项 EV？\n总计：{1}/{2}（{3}%）", total_evs, Pokemon::EV_LIMIT, 100 * total_evs / Pokemon::EV_LIMIT),
            ev_commands, ev_commands.keys.index(ev_cmd)
          )
          break if ev_cmd.nil?
          case ev_cmd
          when :randomize, :max_randomize
            ev_total_target = (ev_cmd == :randomize) ? rand(Pokemon::EV_LIMIT) : Pokemon::EV_LIMIT
            stats.each { |stat| pkmn.ev[stat] = 0 }
            while ev_total_target > 0
              stat = stats.sample
              next if pkmn.ev[stat] >= Pokemon::EV_STAT_LIMIT
              add_val = [1 + rand(Pokemon::EV_STAT_LIMIT / 4), ev_total_target, Pokemon::EV_STAT_LIMIT - pkmn.ev[stat]].min
              next if add_val == 0
              pkmn.ev[stat] += add_val
              ev_total_target -= add_val
            end
            pkmn.calc_stats
            screen.refresh
          else   # Set a particular stat's EVs
            params = ChooseNumberParams.new
            total_other_evs = 0
            stats.each { |stat| total_other_evs += pkmn.ev[stat] if stat != ev_cmd }
            upper_limit = [Pokemon::EV_LIMIT - total_other_evs, Pokemon::EV_STAT_LIMIT].min
            this_value = [pkmn.ev[ev_cmd], upper_limit].min
            params.setRange(0, upper_limit)
            params.setDefaultValue(this_value)
            params.setCancelValue(this_value)
            new_val = screen.choose_number("\\se[]" + _INTL("设置 {1} 的 EV（最大 {2}）。",
                                                            GameData::Stat.get(ev_cmd).name, upper_limit), params)
            if new_val != pkmn.ev[ev_cmd]
              pkmn.ev[ev_cmd] = new_val
              pkmn.calc_stats
              screen.refresh
            end
          end
        end
      when :set_ivs
        iv_cmd = nil
        loop do
          total_ivs = 0
          iv_commands = {}
          stats = []
          GameData::Stat.each_main do |s|
            iv_commands[s.id] = s.name + " (#{pkmn.iv[s.id]})"
            stats.push(s.id)
            total_ivs += pkmn.iv[s.id]
          end
          iv_commands[:randomize] = _INTL("全部随机化")
          iv_cmd ||= iv_commands.keys.first
          hidden_power = pbHiddenPower(pkmn)
          msg = _INTL("要修改哪项 IV？\n觉醒力量：\n{1}，威力 {2}\n总计：{3}/{4}（{5}%）",
                      GameData::Type.get(hidden_power[0]).name, hidden_power[1], total_ivs,
                      stats.length * Pokemon::IV_STAT_LIMIT, 100 * total_ivs / (stats.length * Pokemon::IV_STAT_LIMIT))
          iv_cmd = screen.show_menu(msg, iv_commands, iv_commands.keys.index(iv_cmd))
          break if iv_cmd.nil?
          case iv_cmd
          when :randomize
            stats.each { |stat| pkmn.iv[stat] = rand(Pokemon::IV_STAT_LIMIT + 1) }
            pkmn.calc_stats
            screen.refresh
          else   # Set a particular stat's IVs
            params = ChooseNumberParams.new
            params.setRange(0, Pokemon::IV_STAT_LIMIT)
            params.setDefaultValue(pkmn.iv[iv_cmd])
            params.setCancelValue(pkmn.iv[iv_cmd])
            new_val = screen.choose_number("\\se[]" + _INTL("设置 {1} 的 IV（最大 {2}）。",
                                                            GameData::Stat.get(iv_cmd).name, params.maxNumber), params)
            if new_val != pkmn.iv[iv_cmd]
              pkmn.iv[iv_cmd] = new_val
              pkmn.calc_stats
              screen.refresh
            end
          end
        end
      when :random_pid
        pkmn.personalID = rand(2**16) | (rand(2**16) << 16)
        pkmn.calc_stats
        screen.refresh
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_happiness, {
  "name"   => _INTL("设置亲密度"),
  "parent" => :level_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.happiness)
    new_val = screen.choose_number("\\se[]" + _INTL("设置宝可梦的亲密度（最大 {1}）。", params.maxNumber), params)
    if new_val != pkmn.happiness
      pkmn.happiness = new_val
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :contest_stats, {
  "name"   => _INTL("华丽大赛数值…"),
  "parent" => :level_stats
})

MenuHandlers.add(:pokemon_debug_menu, :set_beauty, {
  "name"   => _INTL("设置美丽"),
  "parent" => :contest_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.beauty)
    new_val = screen.choose_number("\\se[]" + _INTL("设置宝可梦的美丽度（最大 {1}）。", params.maxNumber), params)
    if new_val != pkmn.beauty
      pkmn.beauty = new_val
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_cool, {
  "name"   => _INTL("设置帅气"),
  "parent" => :contest_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.cool)
    new_val = screen.choose_number("\\se[]" + _INTL("设置宝可梦的帅气度（最大 {1}）。", params.maxNumber), params)
    if new_val != pkmn.cool
      pkmn.cool = new_val
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_cute, {
  "name"   => _INTL("设置可爱"),
  "parent" => :contest_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.cute)
    new_val = screen.choose_number("\\se[]" + _INTL("设置宝可梦的可爱度（最大 {1}）。", params.maxNumber), params)
    if new_val != pkmn.cute
      pkmn.cute = new_val
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_smart, {
  "name"   => _INTL("设置聪明"),
  "parent" => :contest_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.smart)
    new_val = screen.choose_number("\\se[]" + _INTL("设置宝可梦的聪明度（最大 {1}）。", params.maxNumber), params)
    if new_val != pkmn.smart
      pkmn.smart = new_val
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_tough, {
  "name"   => _INTL("设置强壮"),
  "parent" => :contest_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.tough)
    new_val = screen.choose_number("\\se[]" + _INTL("设置宝可梦的强壮度（最大 {1}）。", params.maxNumber), params)
    if new_val != pkmn.tough
      pkmn.tough = new_val
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_sheen, {
  "name"   => _INTL("设置光泽"),
  "parent" => :contest_stats,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.sheen)
    new_val = screen.choose_number("\\se[]" + _INTL("设置宝可梦的光泽度（最大 {1}）。", params.maxNumber), params)
    if new_val != pkmn.sheen
      pkmn.sheen = new_val
      screen.refresh
    end
    next false
  }
})

#===============================================================================
# Moves options.
#===============================================================================

MenuHandlers.add(:pokemon_debug_menu, :moves, {
  "name"   => _INTL("招式…"),
  "parent" => :main
})

MenuHandlers.add(:pokemon_debug_menu, :teach_move, {
  "name"   => _INTL("教授招式"),
  "parent" => :moves,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    move = pbChooseMoveList
    if move
      pbLearnMove(pkmn, move)
      screen.refresh
    else
      pbPlayCancelSE
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :forget_move, {
  "name"   => _INTL("遗忘招式"),
  "parent" => :moves,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    move_index = screen.choose_move(pkmn, _INTL("选择要忘记的招式。"))
    if move_index >= 0
      move_name = pkmn.moves[move_index].name
      pkmn.forget_move_at_index(move_index)
      screen.refresh
      screen.show_message(_INTL("{1} 忘记了 {2}。", pkmn.name, move_name))
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :reset_moves, {
  "name"   => _INTL("重置招式"),
  "parent" => :moves,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    pkmn.reset_moves
    screen.refresh
    screen.show_message(_INTL("{1} 的招式已重置。", pkmn.name))
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_move_pp, {
  "name"   => _INTL("设置招式 PP…"),
  "parent" => :moves,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    cmd = nil
    loop do
      commands = {}
      pkmn.moves.each_with_index do |move, i|
        break if !move.id
        if move.total_pp <= 0
          commands[i] = _INTL("{1}（PP：---）", move.name)
        else
          commands[i] = _INTL("{1}（PP：{2}/{3}）", move.name, move.pp, move.total_pp)
        end
      end
      commands[:restore_pp] = _INTL("[恢复全部 PP]")
      cmd ||= commands.keys.first
      cmd = screen.show_menu(_INTL("要修改哪个招式的PP？"), commands, commands.keys.index(cmd))
      break if cmd.nil?
      if cmd == :restore_pp
        pkmn.heal_PP
      elsif pkmn.moves[cmd].total_pp <= 0
        screen.show_message(_INTL("{1} 的 PP 无限。", pkmn.moves[cmd].name))
      else
        move = pkmn.moves[cmd]
        pp_commands = {
          :set_pp  => _INTL("设置PP"),
          :full_pp => _INTL("PP全满"),
          :pp_up   => _INTL("设置PP上限")
        }
        pp_cmd = pp_commands.keys.first
        loop do
          msg = _INTL("{1}：PP {2}/{3}（PP 提升 {4}/3）", move.name, move.pp, move.total_pp, move.ppup)
          pp_cmd = screen.show_menu(msg, pp_commands, pp_commands.keys.index(pp_cmd))
          break if pp_cmd.nil?
          case pp_cmd
          when :set_pp
            params = ChooseNumberParams.new
            params.setRange(0, move.total_pp)
            params.setDefaultValue(move.pp)
            move.pp = screen.choose_number("\\se[]" + _INTL("设置 {1} 的 PP（最大 {2}）。", move.name, params.maxNumber), params)
          when :full_pp
            move.pp = move.total_pp
          when :pp_up
            params = ChooseNumberParams.new
            params.setRange(0, 3)
            params.setDefaultValue(move.ppup)
            new_val = screen.choose_number("\\se[]" + _INTL("设置 {1} 的 PP 提升（最大 {2}）。", move.name, params.maxNumber), params)
            move.ppup = new_val
          end
        end
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_initial_moves, {
  "name"   => _INTL("重置初始招式"),
  "parent" => :moves,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    pkmn.record_first_moves
    screen.refresh
    screen.show_message(_INTL("{1} 的当前招式已设为其最初学会的招式。", pkmn.name))
    next false
  }
})

#===============================================================================
# Other options.
#===============================================================================

MenuHandlers.add(:pokemon_debug_menu, :set_item, {
  "name"   => _INTL("设置持有道具"),
  "parent" => :main,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :change_item => _INTL("修改道具"),
      :delete_item => _INTL("移除道具")
    }
    cmd = commands.keys.first
    loop do
      msg = (pkmn.hasItem?) ? _INTL("道具为 {1}。", pkmn.item.name) : _INTL("没有道具。")
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :change_item
        item = pbChooseItemList(pkmn.item_id)
        if item && item != pkmn.item_id
          pbPlayDecisionSE
          pkmn.item = item
          pkmn.mail = Mail.new(item, _INTL("文本"), $player.name) if GameData::Item.get(item).is_mail?
          screen.refresh
        else
          pbPlayCancelSE
        end
      when :delete_item
        if pkmn.hasItem?
          pkmn.item = nil
          screen.refresh
        end
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_ability, {
  "name"   => _INTL("设置特性"),
  "parent" => :main,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :set_ability_index => _INTL("设置可能觉醒的特性"),
      :give_any_ability  => _INTL("设置任意特性"),
      :reset_ability     => _INTL("重置")
    }
    cmd = commands.keys.first
    loop do
      if pkmn.ability
        msg = _INTL("特性为 {1}（编号 {2}）。", pkmn.ability.name, pkmn.ability_index)
      else
        msg = _INTL("没有特性（编号 {1}）。", pkmn.ability_index)
      end
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :set_ability_index
        abils = pkmn.getAbilityList
        ability_commands = {}
        abil_cmd = nil
        abils.each do |abil|
          ability_commands[abil[1]] = ((abil[1] < 2) ? "" : "(H) ") + GameData::Ability.get(abil[0]).name
          abil_cmd = abil[1] if pkmn.ability_id == abil[0]
        end
        abil_cmd ||= ability_commands.keys.first
        abil_cmd = screen.show_menu(_INTL("选择一个特性。"), ability_commands, ability_commands.keys.index(abil_cmd))
        next if abil_cmd.nil?
        pkmn.ability_index = abil_cmd
        pkmn.ability = nil
        screen.refresh
      when :give_any_ability
        new_ability = pbChooseAbilityList(pkmn.ability_id)
        if new_ability && new_ability != pkmn.ability_id
          pbPlayDecisionSE
          pkmn.ability = new_ability
          screen.refresh
        else
          pbPlayCancelSE
        end
      when :reset_ability
        pkmn.ability_index = nil
        pkmn.ability = nil
        screen.refresh
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_nature, {
  "name"   => _INTL("设置性格"),
  "parent" => :main,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {}
    GameData::Nature.each do |nature|
      if nature.stat_changes.length == 0
        commands[nature.id] = _INTL("{1}（---）", nature.real_name)
        next
      end
      plus_text = ""
      minus_text = ""
      nature.stat_changes.each do |change|
        if change[1] > 0
          plus_text += "/" if !plus_text.empty?
          plus_text += GameData::Stat.get(change[0]).name_brief
        elsif change[1] < 0
          minus_text += "/" if !minus_text.empty?
          minus_text += GameData::Stat.get(change[0]).name_brief
        end
      end
      commands[nature.id] = _INTL("{1}（+{2}，-{3}）", nature.real_name, plus_text, minus_text)
    end
    commands[:reset_nature] = _INTL("【重置】")
    cmd = (commands.keys.include?(pkmn.nature_id)) ? pkmn.nature_id : commands.keys.first
    loop do
      cmd = screen.show_menu(_INTL("性格为 {1}。", pkmn.nature.name), commands, commands.keys.index(cmd))
      break if cmd.nil?
      pkmn.nature = (cmd == :reset_nature) ? nil : cmd
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_gender, {
  "name"   => _INTL("设置性别"),
  "parent" => :main,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    if pkmn.singleGendered?
      screen.show_message(_INTL("{1} 是单性别或无性别。", pkmn.speciesName))
      next false
    end
    commands = {
      :make_male    => _INTL("设为男性"),
      :make_female  => _INTL("设为女性"),
      :reset_gender => _INTL("重置")
    }
    cmd = commands.keys.first
    loop do
      msg = _INTL("未知性别。")
      msg = _INTL("性别为男性。") if pkmn.male?
      msg = _INTL("性别为女性。") if pkmn.female?
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :make_male
        pkmn.makeMale
        screen.show_message(_INTL("{1} 的性别无法修改。", pkmn.name)) if !pkmn.male?
      when :make_female
        pkmn.makeFemale
        screen.show_message(_INTL("{1} 的性别无法修改。", pkmn.name)) if !pkmn.female?
      when :reset_gender
        pkmn.gender = nil
      end
      $player.pokedex.register(pkmn) if !setting_up_battle && !pkmn.egg?
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :species_and_form, {
  "name"   => _INTL("种类/形态…"),
  "parent" => :main,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :set_species => _INTL("设置种类"),
      :set_form    => _INTL("设置形态"),
      :reset_form  => _INTL("移除形态覆盖")
    }
    cmd = commands.keys.first
    loop do
      msg = [_INTL("种类 {1}，形态 {2}。", pkmn.speciesName, pkmn.form),
             _INTL("种类 {1}，形态 {2}（已强制）。", pkmn.speciesName, pkmn.form)][(pkmn.forced_form.nil?) ? 0 : 1]
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :set_species
        species = pbChooseSpeciesList(pkmn.species)
        if species && species != pkmn.species
          pbPlayDecisionSE
          pkmn.species = species
          pkmn.gender = nil
          pkmn.calc_stats
          $player.pokedex.register(pkmn) if !setting_up_battle && !pkmn.egg?
          screen.refresh
        else
          pbPlayCancelSE
        end
      when :set_form
        form_cmd = 0
        form_commands = {}
        GameData::Species.each do |sp|
          next if sp.species != pkmn.species
          form_name = sp.form_name
          form_name = _INTL("未命名形态") if !form_name || form_name.empty?
          form_name = sprintf("%d: %s", sp.form, form_name)
          form_commands[sp.form] = form_name
          form_cmd = sp.form if pkmn.form == sp.form
        end
        form_commands[99_999] = _INTL("自定义数量")
        form_cmd = screen.show_menu(_INTL("设置该宝可梦的形态。"), form_commands, form_commands.keys.index(form_cmd))
        next if form_cmd.nil?
        if form_cmd == 99_999
          params = ChooseNumberParams.new
          params.setRange(0, 999)
          params.setDefaultValue(pkmn.form)
          form_cmd = screen.choose_number("\\se[]" + _INTL("选择自定义形态（最大 {1}）。", params.maxNumber), params)
        end
        if form_cmd != pkmn.form
          if MultipleForms.hasFunction?(pkmn, "getForm")
            next if !screen.show_confirm_message(_INTL("该种类自行决定形态，要覆盖吗？"))
            pkmn.forced_form = form_cmd
          end
          pkmn.form = form_cmd
          $player.pokedex.register(pkmn) if !setting_up_battle && !pkmn.egg?
          screen.refresh
        end
      when :reset_form
        pkmn.forced_form = nil
        screen.refresh
      end
    end
    next false
  }
})

#===============================================================================
# Cosmetic options.
#===============================================================================

MenuHandlers.add(:pokemon_debug_menu, :cosmetic, {
  "name"   => _INTL("外观信息…"),
  "parent" => :main
})

MenuHandlers.add(:pokemon_debug_menu, :set_shininess, {
  "name"   => _INTL("设置异色"),
  "parent" => :cosmetic,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :make_shiny       => _INTL("设为闪光"),
      :make_super_shiny => _INTL("设为异色闪光"),
      :make_not_shiny   => _INTL("设为普通（无闪光）"),
      :reset_shininess  => _INTL("重置")
    }
    cmd = commands.keys.first
    loop do
      msg_idx = (pkmn.shiny?) ? ((pkmn.super_shiny?) ? 1 : 0) : 2
      msg = [_INTL("有闪光。"), _INTL("异色闪光。"), _INTL("普通（无闪光）。")][msg_idx]
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :make_shiny
        pkmn.shiny = true
        pkmn.super_shiny = false
      when :make_super_shiny
        pkmn.super_shiny = true
      when :make_not_shiny
        pkmn.shiny = false
        pkmn.super_shiny = false
      when :reset_shininess
        pkmn.shiny = nil
        pkmn.super_shiny = nil
      end
      $player.pokedex.register(pkmn) if !setting_up_battle && !pkmn.egg?
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_pokeball, {
  "name"   => _INTL("设置精灵球"),
  "parent" => :cosmetic,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {}
    cmd = nil
    GameData::Item.each do |item|
      next if !item.is_poke_ball?
      commands[item.id] = item.name
      cmd = item.id if item.id == pkmn.poke_ball
    end
    commands = commands.sort_by { |key, val| val }.to_h
    cmd ||= commands.keys.first
    loop do
      cmd = screen.show_menu(_INTL("使用了 {1}。", GameData::Item.get(pkmn.poke_ball).name), commands, commands.keys.index(cmd))
      break if cmd.nil?
      pkmn.poke_ball = cmd
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_ribbons, {
  "name"   => _INTL("设置奖章"),
  "parent" => :cosmetic,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    cmd = nil
    loop do
      commands = {}
      GameData::Ribbon.each do |ribbon|
        commands[ribbon.id] = ((pkmn.hasRibbon?(ribbon.id)) ? "[Y]" : "[  ]") + " " + ribbon.name
      end
      commands[:give_all]  = _INTL("全部给予")
      commands[:clear_all] = _INTL("全部清除")
      cmd ||= commands.keys.first
      cmd = screen.show_menu(_INTL("{1} 枚奖章。", pkmn.numRibbons), commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :give_all
        GameData::Ribbon.each { |ribbon| pkmn.giveRibbon(ribbon.id) }
      when :clear_all
        pkmn.clearAllRibbons
      else   # Toggle a specific ribbon
        (pkmn.hasRibbon?(cmd)) ? pkmn.takeRibbon(cmd) : pkmn.giveRibbon(cmd)
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :set_nickname, {
  "name"   => _INTL("设置昵称"),
  "parent" => :cosmetic,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :rename     => _INTL("重命名"),
      :clear_name => _INTL("清除名字")
    }
    cmd = commands.keys.first
    loop do
      species_name = pkmn.speciesName
      msg = [_INTL("{1} 的昵称是 {2}。", species_name, pkmn.name),
             _INTL("{1} 没有昵称。", species_name)][(pkmn.nicknamed?) ? 0 : 1]
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :rename
        old_name = (pkmn.nicknamed?) ? pkmn.name : ""
        pkmn.name = pbEnterPokemonName(_INTL("{1} 的昵称？", species_name),
                                       0, Pokemon::MAX_NAME_SIZE, old_name, pkmn)
      when :clear_name
        pkmn.name = nil
      end
      screen.refresh
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :ownership, {
  "name"   => _INTL("持有情况…"),
  "parent" => :cosmetic,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :make_players      => _INTL("设为玩家所有"),
      :set_ot_name       => _INTL("设置初训家的名字"),
      :set_ot_gender     => _INTL("设置初训家的性别"),
      :random_foreign_id => _INTL("随机信赖ID"),
      :set_id            => _INTL("设置信赖ID")
    }
    cmd = commands.keys.first
    loop do
      gender_text = _INTL("未知性别")
      gender_text = _INTL("男性") if pkmn.owner.male?
      gender_text = _INTL("女性") if pkmn.owner.female?
      public_id_text = sprintf("%05d", pkmn.owner.public_id)
      msg = [_INTL("玩家的宝可梦\n{1}\n{2}\n{3}（{4}）",
                   pkmn.owner.name, gender_text, public_id_text, pkmn.owner.id),
             _INTL("外来宝可梦\n{1}\n{2}\n{3}（{4}）",
                   pkmn.owner.name, gender_text, public_id_text, pkmn.owner.id)][(pkmn.foreign?($player)) ? 1 : 0]
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :make_players
        pkmn.owner = Pokemon::Owner.new_from_trainer($player)
      when :set_ot_name
        pkmn.owner.name = pbEnterPlayerName(_INTL("{1} 的初训家名字？", pkmn.name), 1, Settings::MAX_PLAYER_NAME_SIZE, pkmn.owner.name)
      when :set_ot_gender
        gender_commands = {
          0 => _INTL("男性"),
          1 => _INTL("女性"),
          2 => _INTL("未知")
        }
        gender_cmd = gender_commands.keys.index(pkmn.owner.gender) || gender_commands.keys.first
        gender_cmd = screen.show_menu(_INTL("设置初训家的性别。"), gender_commands, gender_cmd)
        pkmn.owner.gender = gender_cmd if gender_cmd
      when :random_foreign_id
        pkmn.owner.id = $player.make_foreign_ID
      when :set_id
        params = ChooseNumberParams.new
        params.setRange(0, 65_535)
        params.setDefaultValue(pkmn.owner.public_id)
        new_val = screen.choose_number("\\se[]" + _INTL("设置新的 ID（最大 {1}）。", params.maxNumber), params)
        pkmn.owner.id = new_val | (new_val << 16)
      end
    end
    next false
  }
})

#===============================================================================
# Can store/release/trade.
#===============================================================================

MenuHandlers.add(:pokemon_debug_menu, :set_discardable, {
  "name"   => _INTL("设置可丢弃"),
  "parent" => :main,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    cmd = nil
    loop do
      commands = {
        :store   => (pkmn.cannot_store) ? _INTL("不可寄存") : _INTL("可寄存"),
        :release => (pkmn.cannot_release) ? _INTL("不可放生") : _INTL("可放生"),
        :trade   => (pkmn.cannot_trade) ? _INTL("不可交换") : _INTL("可交换")
      }
      cmd ||= commands.keys.first
      cmd = screen.show_menu(_INTL("点击选项即可切换。"), commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :store
        pkmn.cannot_store = !pkmn.cannot_store
      when :release
        pkmn.cannot_release = !pkmn.cannot_release
      when :trade
        pkmn.cannot_trade = !pkmn.cannot_trade
      end
    end
    next false
  }
})

#===============================================================================
# Other options.
#===============================================================================

MenuHandlers.add(:pokemon_debug_menu, :set_egg, {
  "name"        => _INTL("设置蛋"),
  "parent"      => :main,
  "always_show" => false,
  "effect"      => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :make_egg     => _INTL("生成蛋"),
      :make_pokemon => _INTL("生成宝可梦"),
      :one_egg_step => _INTL("把剩余步数设为 1")
    }
    cmd = commands.keys.first
    loop do
      msg = [_INTL("不是蛋。"),
             _INTL("蛋（还需 {1} 步孵化）。", pkmn.steps_to_hatch)][(pkmn.egg?) ? 1 : 0]
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :make_egg
        if !pkmn.egg? && (pbHasEgg?(pkmn.species) ||
           screen.show_confirm_message(_INTL("{1} 变成蛋不合法。仍要设为蛋吗？", pkmn.speciesName)))
          pkmn.level          = Settings::EGG_LEVEL
          pkmn.calc_stats
          pkmn.name           = _INTL("蛋")
          pkmn.steps_to_hatch = pkmn.species_data.hatch_steps
          pkmn.hatched_map    = 0
          pkmn.obtain_method  = 1
          screen.refresh
        end
      when :make_pokemon
        if pkmn.egg?
          pkmn.name           = nil
          pkmn.steps_to_hatch = 0
          pkmn.hatched_map    = 0
          pkmn.obtain_method  = 0
          $player.pokedex.register(pkmn) if !setting_up_battle
          screen.refresh
        end
      when :one_egg_step
        pkmn.steps_to_hatch = 1 if pkmn.egg?
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :shadow_pkmn, {
  "name"   => _INTL("暗影宝可梦…"),
  "parent" => :main,
  "effect" => proc { |pkmn, party_index, setting_up_battle, screen|
    commands = {
      :make_shadow     => _INTL("生成暗影宝可梦"),
      :set_heart_gauge => _INTL("设置心之刻度"),
      :purify          => _INTL("净化")
    }
    cmd = commands.keys.first
    loop do
      msg = [_INTL("不是暗影宝可梦。"),
             _INTL("心灵槽为 {1}（阶段 {2}）。", pkmn.heart_gauge, pkmn.heartStage)][(pkmn.shadowPokemon?) ? 1 : 0]
      cmd = screen.show_menu(msg, commands, commands.keys.index(cmd))
      break if cmd.nil?
      case cmd
      when :make_shadow
        if pkmn.shadowPokemon?
          screen.show_message(_INTL("{1} 已经是黑暗宝可梦。", pkmn.name))
        else
          pkmn.makeShadow
          screen.refresh
        end
      when :set_heart_gauge
        if pkmn.shadowPokemon?
          params = ChooseNumberParams.new
          params.setRange(0, pkmn.max_gauge_size)
          params.setDefaultValue(pkmn.heart_gauge)
          new_val = screen.choose_number("\\se[]" + _INTL("设置心灵槽（最大 {1}）。", params.maxNumber), params)
          if new_val != pkmn.heart_gauge
            pkmn.adjustHeart(new_val - pkmn.heart_gauge)
            pkmn.check_ready_to_purify
          end
        else
          screen.show_message(_INTL("{1} 不是黑暗宝可梦。", pkmn.name))
        end
      when :purify
        if pkmn.shadowPokemon?
          pkmn.adjustHeart(-pkmn.heart_gauge)
          pbPurify(pkmn, screen)
        else
          screen.show_message(_INTL("{1} 不是黑暗宝可梦。", pkmn.name))
        end
      end
    end
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :mystery_gift, {
  "name"        => _INTL("神秘礼物"),
  "parent"      => :main,
  "always_show" => false,
  "effect"      => proc { |pkmn, party_index, setting_up_battle, screen|
    pbCreateMysteryGift(0, pkmn)
    next false
  }
})

MenuHandlers.add(:pokemon_debug_menu, :duplicate, {
  "name"        => _INTL("复制"),
  "parent"      => :main,
  "always_show" => false,
  "effect"      => proc { |pkmn, party_index, setting_up_battle, screen|
    next false if !screen.show_confirm_message(_INTL("确定要复制这只宝可梦吗？"))
    cloned_pkmn = pkmn.clone
    case screen
    when UI::Party
      pbStorePokemon(cloned_pkmn)   # Add to party, or to storage if party is full
      screen.refresh_party
      screen.refresh
    when UI::PokemonStorage
      if screen.storage.pbMoveCaughtToParty(cloned_pkmn)
        screen.show_message(_INTL("复制的宝可梦已放进你的队伍。")) if party_index[0] >= 0
      else
        old_box = screen.storage.currentBox
        new_box = screen.storage.pbStoreCaught(cloned_pkmn)
        if new_box < 0
          screen.show_message(_INTL("所有仓库格子都已满。"))
        elsif new_box != old_box
          screen.show_message(_INTL("重复的宝可梦已移到「{1}」仓库。", screen.storage[new_box].name))
          screen.storage.currentBox = old_box
        end
      end
      screen.refresh
    end
    next true
  }
})

MenuHandlers.add(:pokemon_debug_menu, :delete, {
  "name"        => _INTL("删除"),
  "parent"      => :main,
  "always_show" => false,
  "effect"      => proc { |pkmn, party_index, setting_up_battle, screen|
    next false if !screen.show_confirm_message(_INTL("确定要删除这只宝可梦吗？"))
    case screen
    when UI::Party
      screen.party.delete_at(party_index)
      screen.refresh_party
    when UI::PokemonStorage
      screen.visuals.release_pokemon(true)
      screen.storage.pbDelete(party_index[0], party_index[1]) if !screen.holding_pokemon?
    end
    screen.refresh
    next true
  }
})
