#===============================================================================
# HP/Status options
#===============================================================================
MenuHandlers.add(:battle_pokemon_debug_menu, :hp_status_menu, {
  "name"   => _INTL("HP/状态…"),
  "parent" => :main,
  "usage"  => :both
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_hp, {
  "name"   => _INTL("设置 HP"),
  "parent" => :hp_status_menu,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.egg?
      pbMessage("\\ts[]" + _INTL("{1} 是蛋。", pkmn.name))
      next
    elsif battler && pkmn.totalhp == 1
      pbMessage("\\ts[]" + _INTL("无法修改 HP：{1} 的最大 HP 为 1，且正在战斗中。", pkmn.name))
      next
    end
    min_hp = (battler) ? 1 : 0
    params = ChooseNumberParams.new
    params.setRange(min_hp, pkmn.totalhp)
    params.setDefaultValue(pkmn.hp)
    new_hp = pbMessageChooseNumber(
      "\\ts[]" + _INTL("设置 {1} 的 HP（{2}-{3}）。", (battler) ? battler.pbThis(true) : pkmn.name, min_hp, pkmn.totalhp),
      params
    )
    next if new_hp == pkmn.hp
    (battler || pkmn).hp = new_hp
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_status, {
  "name"   => _INTL("设置状态"),
  "parent" => :hp_status_menu,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.egg?
      pbMessage("\\ts[]" + _INTL("{1} 是蛋。", pkmn.name))
      next
    elsif pkmn.hp <= 0
      pbMessage("\\ts[]" + _INTL("{1} 已濒死，无法修改状态。", pkmn.name))
      next
    end
    cmd = 0
    commands = [_INTL("【治愈】")]
    ids = [:NONE]
    GameData::Status.each do |s|
      next if s.id == :NONE
      commands.push(_INTL("设置 {1}", s.name))
      ids.push(s.id)
    end
    loop do
      msg = _INTL("当前状态：{1}", GameData::Status.get(pkmn.status).name)
      if pkmn.status == :SLEEP
        msg += " " + _INTL("（回合：{1}）", pkmn.statusCount)
      elsif pkmn.status == :POISON && pkmn.statusCount > 0
        if battler
          msg += " " + _INTL("（剧毒，计数：{1}）", battler.effects[PBEffects::Toxic])
        else
          msg += " " + _INTL("（中毒）")
        end
      end
      cmd = pbMessage("\\ts[]" + msg, commands, -1, nil, cmd)
      break if cmd < 0
      case cmd
      when 0   # Cure
        if battler
          battler.status = :NONE
        else
          pkmn.heal_status
        end
      else   # Give status problem
        pkmn_name = (battler) ? battler.pbThis(true) : pkmn.name
        case ids[cmd]
        when :SLEEP
          params = ChooseNumberParams.new
          params.setRange(0, 99)
          params.setDefaultValue((pkmn.status == :SLEEP) ? pkmn.statusCount : 3)
          params.setCancelValue(-1)
          count = pbMessageChooseNumber("\\ts[]" + _INTL("设置 {1} 的睡眠计数（0-99）。", pkmn_name), params)
          next if count < 0
          (battler || pkmn).statusCount = count
        when :POISON
          if pbConfirmMessage("\\ts[]" + _INTL("要让 {1} 陷入剧毒状态吗？", pkmn_name))
            if battler
              params = ChooseNumberParams.new
              params.setRange(0, 16)
              params.setDefaultValue(battler.effects[PBEffects::Toxic])
              params.setCancelValue(-1)
              count = pbMessageChooseNumber(
                "\\ts[]" + _INTL("设置 {1} 的剧毒计数（0-16）。", pkmn_name), params
              )
              next if count < 0
              battler.statusCount = 1
              battler.effects[PBEffects::Toxic] = count
            else
              pkmn.statusCount = 1
            end
          else
            (battler || pkmn).statusCount = 0
          end
        end
        (battler || pkmn).status = ids[cmd]
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :full_heal, {
  "name"   => _INTL("恢复 HP 与状态"),
  "parent" => :hp_status_menu,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.egg?
      pbMessage("\\ts[]" + _INTL("{1} 是蛋。", pkmn.name))
      next
    end
    if battler
      battler.hp = battler.totalhp
      battler.status = :NONE
    else
      pkmn.heal_HP
      pkmn.heal_status
    end
  }
})

#===============================================================================
# Level/stats options
#===============================================================================
MenuHandlers.add(:battle_pokemon_debug_menu, :level_stats, {
  "name"   => _INTL("数值/等级…"),
  "parent" => :main,
  "usage"  => :both
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_stat_stages, {
  "name"   => _INTL("设置能力等级"),
  "parent" => :level_stats,
  "usage"  => :battler,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.egg?
      pbMessage("\\ts[]" + _INTL("{1} 是蛋。", pkmn.name))
      next
    end
    cmd = 0
    loop do
      commands = []
      stat_ids = []
      GameData::Stat.each_battle do |stat|
        command_name = stat.name + ": "
        command_name += "+" if battler.stages[stat.id] > 0
        command_name += battler.stages[stat.id].to_s
        commands.push(command_name)
        stat_ids.push(stat.id)
      end
      commands.push(_INTL("【全部重置】"))
      cmd = pbMessage("\\ts[]" + _INTL("选择要修改的能力等级。"), commands, -1, nil, cmd)
      break if cmd < 0
      if cmd < stat_ids.length   # Set a stat
        params = ChooseNumberParams.new
        params.setRange(-Battle::Battler::STAT_STAGE_MAXIMUM, Battle::Battler::STAT_STAGE_MAXIMUM)
        params.setNegativesAllowed(true)
        params.setDefaultValue(battler.stages[stat_ids[cmd]])
        value = pbMessageChooseNumber(
          "\\ts[]" + _INTL("设置 {1} 的阶数。", GameData::Stat.get(stat_ids[cmd]).name), params
        )
        battler.stages[stat_ids[cmd]] = value
      else   # Reset all stats
        GameData::Stat.each_battle { |stat| battler.stages[stat.id] = 0 }
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_stat_values, {
  "name"   => _INTL("设置能力值"),
  "parent" => :level_stats,
  "usage"  => :battler,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.egg?
      pbMessage("\\ts[]" + _INTL("{1} 是蛋。", pkmn.name))
      next
    end
    stat_ids = []
    stat_vals = []
    GameData::Stat.each_main_battle do |stat|
      stat_ids.push(stat.id)
      case stat.id
      when :ATTACK          then stat_vals.push(battler.attack)
      when :DEFENSE         then stat_vals.push(battler.defense)
      when :SPECIAL_ATTACK  then stat_vals.push(battler.spatk)
      when :SPECIAL_DEFENSE then stat_vals.push(battler.spdef)
      when :SPEED           then stat_vals.push(battler.speed)
      else                       stat_vals.push(1)
      end
    end
    cmd = 0
    loop do
      commands = []
      GameData::Stat.each_main_battle do |stat|
        command_name = stat.name + ": " + stat_vals[stat_ids.index(stat.id)].to_s
        commands.push(command_name)
      end
      commands.push(_INTL("【全部重置】"))
      cmd = pbMessage("\\ts[]" + _INTL("选择要修改的能力数值。"), commands, -1, nil, cmd)
      break if cmd < 0
      if cmd < stat_ids.length   # Set a stat
        params = ChooseNumberParams.new
        params.setRange(1, 9999)
        params.setDefaultValue(stat_vals[cmd])
        value = pbMessageChooseNumber(
          "\\ts[]" + _INTL("设置 {1} 的值。", GameData::Stat.get(stat_ids[cmd]).name), params
        )
        case stat_ids[cmd]
        when :ATTACK          then battler.attack  = value
        when :DEFENSE         then battler.defense = value
        when :SPECIAL_ATTACK  then battler.spatk   = value
        when :SPECIAL_DEFENSE then battler.spdef   = value
        when :SPEED           then battler.speed   = value
        end
        stat_vals[cmd] = value
      else   # Reset all stat values
        battler.pbUpdate
        GameData::Stat.each_main_battle do |stat|
          case stat.id
          when :ATTACK          then stat_vals[stat_ids.index(stat.id)] = battler.attack
          when :DEFENSE         then stat_vals[stat_ids.index(stat.id)] = battler.defense
          when :SPECIAL_ATTACK  then stat_vals[stat_ids.index(stat.id)] = battler.spatk
          when :SPECIAL_DEFENSE then stat_vals[stat_ids.index(stat.id)] = battler.spdef
          when :SPEED           then stat_vals[stat_ids.index(stat.id)] = battler.speed
          else                       stat_vals[stat_ids.index(stat.id)] = 1
          end
        end
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_level, {
  "name"   => _INTL("设置等级"),
  "parent" => :level_stats,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.egg?
      pbMessage("\\ts[]" + _INTL("{1} 是蛋。", pkmn.name))
      next
    end
    params = ChooseNumberParams.new
    params.setRange(1, GameData::GrowthRate.max_level)
    params.setDefaultValue(pkmn.level)
    level = pbMessageChooseNumber(
      "\\ts[]" + _INTL("设置宝可梦的等级（最大 {1}）。", params.maxNumber), params
    )
    if level != pkmn.level
      pkmn.level = level
      pkmn.calc_stats
      battler&.pbUpdate
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_exp, {
  "name"   => _INTL("设置经验"),
  "parent" => :level_stats,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.egg?
      pbMessage("\\ts[]" + _INTL("{1} 是蛋。", pkmn.name))
      next
    end
    min_exp = pkmn.growth_rate.minimum_exp_for_level(pkmn.level)
    max_exp = pkmn.growth_rate.minimum_exp_for_level(pkmn.level + 1)
    if min_exp == max_exp
      pbMessage("\\ts[]" + _INTL("{1} 已到最高等级。", pkmn.name))
      next
    end
    params = ChooseNumberParams.new
    params.setRange(min_exp, max_exp - 1)
    params.setDefaultValue(pkmn.exp)
    new_exp = pbMessageChooseNumber(
      "\\ts[]" + _INTL("设置宝可梦的经验值（范围 {1}-{2}）。", min_exp, max_exp - 1), params
    )
    pkmn.exp = new_exp if new_exp != pkmn.exp
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :hidden_values, {
  "name"   => _INTL("努力值/个体值…"),
  "parent" => :level_stats,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    cmd = 0
    loop do
      cmd = pbMessage("\\ts[]" + _INTL("选择要编辑的隐藏数值。"),
                      [_INTL("设置努力值"), _INTL("设置个体值")], -1, nil, cmd)
      break if cmd < 0
      case cmd
      when 0   # Set EVs
        cmd2 = 0
        loop do
          total_evs = 0
          ev_commands = []
          ev_id = []
          GameData::Stat.each_main do |s|
            ev_commands.push(s.name + " (#{pkmn.ev[s.id]})")
            ev_id.push(s.id)
            total_evs += pkmn.ev[s.id]
          end
          ev_commands.push(_INTL("全部随机"))
          ev_commands.push(_INTL("全部随机到最大"))
          cmd2 = pbMessage("\\ts[]" + _INTL("要修改哪项 EV？\n总计：{1}/{2}（{3}%）",
                                            total_evs, Pokemon::EV_LIMIT, 100 * total_evs / Pokemon::EV_LIMIT),
                           ev_commands, -1, nil, cmd2)
          break if cmd2 < 0
          if cmd2 < ev_id.length
            params = ChooseNumberParams.new
            upperLimit = 0
            GameData::Stat.each_main { |s| upperLimit += pkmn.ev[s.id] if s.id != ev_id[cmd2] }
            upperLimit = Pokemon::EV_LIMIT - upperLimit
            upperLimit = [upperLimit, Pokemon::EV_STAT_LIMIT].min
            thisValue = [pkmn.ev[ev_id[cmd2]], upperLimit].min
            params.setRange(0, upperLimit)
            params.setDefaultValue(thisValue)
            params.setCancelValue(thisValue)
            f = pbMessageChooseNumber("\\ts[]" + _INTL("设置 {1} 的 EV（最大 {2}）。",
                                                       GameData::Stat.get(ev_id[cmd2]).name, upperLimit), params)
            if f != pkmn.ev[ev_id[cmd2]]
              pkmn.ev[ev_id[cmd2]] = f
              pkmn.calc_stats
              battler&.pbUpdate
            end
          else   # (Max) Randomise all
            evTotalTarget = Pokemon::EV_LIMIT
            if cmd2 == ev_commands.length - 2   # Randomize all (not max)
              evTotalTarget = rand(Pokemon::EV_LIMIT)
            end
            GameData::Stat.each_main { |s| pkmn.ev[s.id] = 0 }
            while evTotalTarget > 0
              r = rand(ev_id.length)
              next if pkmn.ev[ev_id[r]] >= Pokemon::EV_STAT_LIMIT
              addVal = 1 + rand(Pokemon::EV_STAT_LIMIT / 4)
              addVal = addVal.clamp(0, evTotalTarget)
              addVal = addVal.clamp(0, Pokemon::EV_STAT_LIMIT - pkmn.ev[ev_id[r]])
              next if addVal == 0
              pkmn.ev[ev_id[r]] += addVal
              evTotalTarget -= addVal
            end
            pkmn.calc_stats
            battler&.pbUpdate
          end
        end
      when 1   # Set IVs
        cmd2 = 0
        loop do
          hiddenpower = pbHiddenPower(pkmn)
          totaliv = 0
          ivcommands = []
          iv_id = []
          GameData::Stat.each_main do |s|
            ivcommands.push(s.name + " (#{pkmn.iv[s.id]})")
            iv_id.push(s.id)
            totaliv += pkmn.iv[s.id]
          end
          msg = _INTL("要修改哪项 IV？\n觉醒力量：{1}，威力 {2}\n总计：{3}/{4}（{5}%）",
                      GameData::Type.get(hiddenpower[0]).name, hiddenpower[1], totaliv,
                      iv_id.length * Pokemon::IV_STAT_LIMIT, 100 * totaliv / (iv_id.length * Pokemon::IV_STAT_LIMIT))
          ivcommands.push(_INTL("全部随机"))
          cmd2 = pbMessage("\\ts[]\\l[3]" + msg, ivcommands, -1, nil, cmd2)
          break if cmd2 < 0
          if cmd2 < iv_id.length
            params = ChooseNumberParams.new
            params.setRange(0, Pokemon::IV_STAT_LIMIT)
            params.setDefaultValue(pkmn.iv[iv_id[cmd2]])
            params.setCancelValue(pkmn.iv[iv_id[cmd2]])
            f = pbMessageChooseNumber("\\ts[]" + _INTL("设置 {1} 的 IV（最大 31）。",
                                                       GameData::Stat.get(iv_id[cmd2]).name), params)
            if f != pkmn.iv[iv_id[cmd2]]
              pkmn.iv[iv_id[cmd2]] = f
              pkmn.calc_stats
              battler&.pbUpdate
            end
          else   # Randomise all
            GameData::Stat.each_main { |s| pkmn.iv[s.id] = rand(Pokemon::IV_STAT_LIMIT + 1) }
            pkmn.calc_stats
            battler&.pbUpdate
          end
        end
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_happiness, {
  "name"   => _INTL("设置亲密度"),
  "parent" => :level_stats,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    params = ChooseNumberParams.new
    params.setRange(0, 255)
    params.setDefaultValue(pkmn.happiness)
    h = pbMessageChooseNumber("\\ts[]" + _INTL("设置该宝可梦的亲密度（最高 255）。"), params)
    pkmn.happiness = h if h != pkmn.happiness
  }
})

#===============================================================================
# Types
#===============================================================================
MenuHandlers.add(:battle_pokemon_debug_menu, :set_types, {
  "name"   => _INTL("设置属性"),
  "parent" => :main,
  "usage"  => :battler,
  "effect" => proc { |pkmn, battler, battle|
    max_main_types = 5   # Arbitrary value, could be any number
    cmd = 0
    loop do
      commands = []
      types = []
      max_main_types.times do |i|
        type = battler.types[i]
        type_name = (type) ? GameData::Type.get(type).name : "-"
        commands.push(_INTL("属性 {1}：{2}", i + 1, type_name))
        types.push(type)
      end
      extra_type = battler.effects[PBEffects::ExtraType]
      extra_type_name = (extra_type) ? GameData::Type.get(extra_type).name : "-"
      commands.push(_INTL("附加属性：{1}", extra_type_name))
      types.push(extra_type)
      msg = _INTL("有效属性：{1}", battler.pbTypes(true).map { |t| GameData::Type.get(t).name }.join("/"))
      msg += "\n" + _INTL("（选两次同一个属性即可移除。）")
      cmd = pbMessage("\\ts[]" + msg, commands, -1, nil, cmd)
      break if cmd < 0
      old_type = types[cmd]
      new_type = pbChooseTypeList(old_type)
      if new_type
        if new_type == old_type
          if pbConfirmMessage(_INTL("要移除这个属性吗？"))
            if cmd < max_main_types
              battler.types[cmd] = nil
            else
              battler.effects[PBEffects::ExtraType] = nil
            end
            battler.types.compact!
          end
        elsif cmd < max_main_types
          battler.types[cmd] = new_type
        else
          battler.effects[PBEffects::ExtraType] = new_type
        end
      end
    end
  }
})

#===============================================================================
# Moves options
#===============================================================================
MenuHandlers.add(:battle_pokemon_debug_menu, :moves, {
  "name"   => _INTL("招式…"),
  "parent" => :main,
  "usage"  => :both
})

MenuHandlers.add(:battle_pokemon_debug_menu, :teach_move, {
  "name"   => _INTL("教授招式"),
  "parent" => :moves,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.numMoves >= Pokemon::MAX_MOVES
      pbMessage("\\ts[]" + _INTL("{1} 已经学会 {2} 个招式，需要先遗忘一个。",
                                 pkmn.name, pkmn.numMoves))
      next
    end
    new_move = pbChooseMoveList
    next if !new_move
    move_name = GameData::Move.get(new_move).name
    if pkmn.hasMove?(new_move)
      pbMessage("\\ts[]" + _INTL("{1} 已经学会 {2}。", pkmn.name, move_name))
      next
    end
    pkmn.learn_move(new_move)
    battler&.moves&.push(Battle::Move.from_pokemon_move(battle, pkmn.moves.last))
    pbMessage("\\ts[]" + _INTL("{1} 学会了 {2}！", pkmn.name, move_name))
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :forget_move, {
  "name"   => _INTL("遗忘招式"),
  "parent" => :moves,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    move_names = []
    move_indices = []
    pkmn.moves.each_with_index do |move, index|
      next if !move || !move.id
      if move.total_pp <= 0
        move_names.push(_INTL("{1}（PP：---）", move.name))
      else
        move_names.push(_INTL("{1}（PP：{2}/{3}）", move.name, move.pp, move.total_pp))
      end
      move_indices.push(index)
    end
    cmd = pbMessage("\\ts[]" + _INTL("要忘记哪个招式？"), move_names, -1)
    next if cmd < 0
    old_move_name = pkmn.moves[move_indices[cmd]].name
    pkmn.forget_move_at_index(move_indices[cmd])
    battler&.moves&.delete_at(move_indices[cmd])
    pbMessage("\\ts[]" + _INTL("{1} 忘记了 {2}。", pkmn.name, old_move_name))
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_move_pp, {
  "name"   => _INTL("设置招式 PP"),
  "parent" => :moves,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    cmd = 0
    loop do
      move_names = []
      move_indices = []
      pkmn.moves.each_with_index do |move, index|
        next if !move || !move.id
        if move.total_pp <= 0
          move_names.push(_INTL("{1}（PP：---）", move.name))
        else
          move_names.push(_INTL("{1}（PP：{2}/{3}）", move.name, move.pp, move.total_pp))
        end
        move_indices.push(index)
      end
      commands = move_names + [_INTL("恢复全部PP")]
      cmd = pbMessage("\\ts[]" + _INTL("要修改哪个招式的PP？"), commands, -1, nil, cmd)
      break if cmd < 0
      if cmd >= 0 && cmd < move_names.length   # Move
        move = pkmn.moves[move_indices[cmd]]
        move_name = move.name
        if move.total_pp <= 0
          pbMessage("\\ts[]" + _INTL("{1} 的 PP 无限。", move_name))
        else
          cmd2 = 0
          loop do
            msg = _INTL("{1}：PP {2}/{3}（PP 提升 {4}/3）", move_name, move.pp, move.total_pp, move.ppup)
            cmd2 = pbMessage("\\ts[]" + msg,
                             [_INTL("设置PP"), _INTL("PP全满"), _INTL("设置PP上限")], -1, nil, cmd2)
            break if cmd2 < 0
            case cmd2
            when 0   # Change PP
              params = ChooseNumberParams.new
              params.setRange(0, move.total_pp)
              params.setDefaultValue(move.pp)
              h = pbMessageChooseNumber(
                "\\ts[]" + _INTL("设置 {1} 的 PP（最大 {2}）。", move_name, move.total_pp), params
              )
              move.pp = h
              if battler && battler.moves[move_indices[cmd]].id == move.id
                battler.moves[move_indices[cmd]].pp = move.pp
              end
            when 1   # Full PP
              move.pp = move.total_pp
              if battler && battler.moves[move_indices[cmd]].id == move.id
                battler.moves[move_indices[cmd]].pp = move.pp
              end
            when 2   # Change PP Up
              params = ChooseNumberParams.new
              params.setRange(0, 3)
              params.setDefaultValue(move.ppup)
              h = pbMessageChooseNumber(
                "\\ts[]" + _INTL("设置 {1} 的 PP 提升（最大 3）。", move_name), params
              )
              move.ppup = h
              move.pp = move.total_pp if move.pp > move.total_pp
              if battler && battler.moves[move_indices[cmd]].id == move.id
                battler.moves[move_indices[cmd]].pp = move.pp
              end
            end
          end
        end
      elsif cmd == commands.length - 1   # Restore all PP
        pkmn.heal_PP
        if battler
          battler.moves.each { |m| m.pp = m.total_pp }
        end
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :reset_moves, {
  "name"   => _INTL("重置招式"),
  "parent" => :moves,
  "usage"  => :pokemon,
  "effect" => proc { |pkmn, battler, battle|
    next if !pbConfirmMessage(_INTL("要把它换成野生时会会的招式吗？"))
    pkmn.reset_moves
    pbMessage("\\ts[]" + _INTL("{1} 的招式已重置。", pkmn.name))
  }
})

#===============================================================================
# Other options
#===============================================================================
MenuHandlers.add(:battle_pokemon_debug_menu, :set_item, {
  "name"   => _INTL("设置持有道具"),
  "parent" => :main,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    cmd = 0
    commands = [
      _INTL("修改道具"),
      _INTL("移除道具")
    ]
    loop do
      msg = (pkmn.hasItem?) ? _INTL("道具为 {1}。", pkmn.item.name) : _INTL("没有道具。")
      cmd = pbMessage("\\ts[]" + msg, commands, -1, nil, cmd)
      break if cmd < 0
      case cmd
      when 0   # Change item
        item = pbChooseItemList(pkmn.item_id)
        if item && item != pkmn.item_id
          (battler || pkmn).item = item
          if GameData::Item.get(item).is_mail?
            pkmn.mail = Mail.new(item, _INTL("文本"), $player.name)
          end
        end
      when 1   # Remove item
        if pkmn.hasItem?
          (battler || pkmn).item = nil
          pkmn.mail = nil
        end
      else
        break
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_ability, {
  "name"   => _INTL("设置特性"),
  "parent" => :main,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    cmd = 0
    commands = []
    commands.push(_INTL("设置宝可梦的特性"))
    commands.push(_INTL("设置战斗对象的特性")) if battler
    commands.push(_INTL("重置"))
    loop do
      if battler
        msg = _INTL("战斗者的特性是 {1}，宝可梦的特性是 {2}。",
                    battler.abilityName, pkmn.ability.name)
      else
        msg = _INTL("宝可梦的特性是 {1}。", pkmn.ability.name)
      end
      cmd = pbMessage("\\ts[]" + msg, commands, -1, nil, cmd)
      break if cmd < 0
      cmd = 2 if cmd >= 1 && !battler   # Correct command for Pokémon (no battler)
      case cmd
      when 0   # Set ability for Pokémon
        new_ability = pbChooseAbilityList(pkmn.ability_id)
        if new_ability && new_ability != pkmn.ability_id
          pkmn.ability = new_ability
          battler.ability = pkmn.ability if battler
        end
      when 1   # Set ability for battler
        if battler
          new_ability = pbChooseAbilityList(battler.ability_id)
          if new_ability && new_ability != battler.ability_id
            battler.ability = new_ability
          end
        else
          pbMessage(_INTL("这只宝可梦不在战斗中。"))
        end
      when 2   # Reset
        pkmn.ability_index = nil
        pkmn.ability = nil
        battler.ability = pkmn.ability if battler
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_nature, {
  "name"   => _INTL("设置性格"),
  "parent" => :main,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    commands = []
    ids = []
    GameData::Nature.each do |nature|
      if nature.stat_changes.length == 0
        commands.push(_INTL("{1}（---）", nature.real_name))
      else
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
        commands.push(_INTL("{1}（+{2}，-{3}）", nature.real_name, plus_text, minus_text))
      end
      ids.push(nature.id)
    end
    commands.push(_INTL("【重置】"))
    cmd = ids.index(pkmn.nature_id || ids[0])
    loop do
      msg = _INTL("性格为 {1}。", pkmn.nature.name)
      cmd = pbMessage("\\ts[]" + msg, commands, -1, nil, cmd)
      break if cmd < 0
      if cmd >= 0 && cmd < commands.length - 1   # Set nature
        pkmn.nature = ids[cmd]
      elsif cmd == commands.length - 1   # Reset
        pkmn.nature = nil
      end
      battler&.pbUpdate
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_gender, {
  "name"   => _INTL("设置性别"),
  "parent" => :main,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    if pkmn.singleGendered?
      pbMessage("\\ts[]" + _INTL("{1} 是单性别或无性别。", pkmn.speciesName))
      next
    end
    cmd = 0
    loop do
      msg = [_INTL("性别为男性。"), _INTL("性别为女性。")][pkmn.male? ? 0 : 1]
      cmd = pbMessage("\\ts[]" + msg,
                      [_INTL("设为男性"), _INTL("设为女性"), _INTL("重置")], -1, nil, cmd)
      break if cmd < 0
      case cmd
      when 0   # Make male
        pkmn.makeMale
        pbMessage("\\ts[]" + _INTL("{1} 的性别无法修改。", pkmn.name)) if !pkmn.male?
      when 1   # Make female
        pkmn.makeFemale
        pbMessage("\\ts[]" + _INTL("{1} 的性别无法修改。", pkmn.name)) if !pkmn.female?
      when 2   # Reset
        pkmn.gender = nil
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_form, {
  "name"   => _INTL("设置形态"),
  "parent" => :main,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    cmd = 0
    formcmds = [[], []]
    GameData::Species.each do |sp|
      next if sp.species != pkmn.species
      form_name = sp.form_name
      form_name = _INTL("未命名形态") if !form_name || form_name.empty?
      form_name = sprintf("%d: %s", sp.form, form_name)
      formcmds[0].push(sp.form)
      formcmds[1].push(form_name)
      cmd = formcmds[0].length - 1 if pkmn.form == sp.form
    end
    if formcmds[0].length <= 1
      pbMessage("\\ts[]" + _INTL("种类 {1} 只有一个形态。", pkmn.speciesName))
      next
    end
    loop do
      cmd = pbMessage("\\ts[]" + _INTL("形态为 {1}。", pkmn.form), formcmds[1], -1, nil, cmd)
      break if cmd < 0
      f = formcmds[0][cmd]
      next if f == pkmn.form
      pkmn.forced_form = nil
      if MultipleForms.hasFunction?(pkmn, "getForm")
        next if !pbConfirmMessage(_INTL("该种类自行决定形态，要覆盖吗？"))
        pkmn.forced_form = f
      end
      pkmn.form_simple = f
      battler.form = pkmn.form if battler
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_species, {
  "name"   => _INTL("设置种类"),
  "parent" => :main,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    species = pbChooseSpeciesList(pkmn.species)
    if species && species != pkmn.species
      pkmn.species = species
      battler.species = species if battler
      battler&.pbUpdate(true)
      battler.name = pkmn.name if battler
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_shininess, {
  "name"   => _INTL("设置异色"),
  "parent" => :main,
  "usage"  => :both,
  "effect" => proc { |pkmn, battler, battle|
    cmd = 0
    loop do
      msg_idx = pkmn.shiny? ? (pkmn.super_shiny? ? 1 : 0) : 2
      msg = [_INTL("有闪光。"), _INTL("异色闪光。"), _INTL("普通（无闪光）。")][msg_idx]
      cmd = pbMessage("\\ts[]" + msg,
                      [_INTL("设为闪光"),
                       _INTL("设为异色闪光"),
                       _INTL("设为普通（无闪光）"),
                       _INTL("重置")], -1, nil, cmd)
      break if cmd < 0
      case cmd
      when 0   # Make shiny
        pkmn.shiny = true
        pkmn.super_shiny = false
      when 1   # Make super shiny
        pkmn.super_shiny = true
      when 2   # Make normal
        pkmn.shiny = false
        pkmn.super_shiny = false
      when 3   # Reset
        pkmn.shiny = nil
        pkmn.super_shiny = nil
      end
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :shadow_pokemon, {
  "name"   => _INTL("暗影宝可梦"),
  "parent" => :main,
  "usage"  => :battler,
  "effect" => proc { |pkmn, battler, battle|
    if battler.shadowPokemon?
      loop do
        if battler.inHyperMode?
          msg = _INTL("暗影宝可梦（超级模式中）")
        else
          msg = _INTL("暗影宝可梦（非超级模式）")
        end
        cmd = pbMessage("\\ts[]" + msg, [_INTL("切换超级模式"), _INTL("取消")], -1, nil, 0)
        break if cmd != 0
        if battler.inHyperMode?
          pkmn.hyper_mode = false
        elsif battler.fainted? || !battler.pbOwnedByPlayer?
          pbMessage("\\ts[]" + _INTL("宝可梦已失去意识或不是玩家的，无法进入超级模式。"))
        else
          pkmn.hyper_mode = true
        end
      end
    else
      pbMessage("\\ts[]" + _INTL("这不是暗影宝可梦。"))
    end
  }
})

MenuHandlers.add(:battle_pokemon_debug_menu, :set_effects, {
  "name"   => _INTL("设置效果"),
  "parent" => :main,
  "usage"  => :battler,
  "effect" => proc { |pkmn, battler, battle|
    editor = Battle::DebugSetEffects.new(battle, :battler, battler.index)
    editor.update
    editor.dispose
  }
})
