# AI skill levels:
#           0:     Wild Pokémon
#           1-31:  Basic trainer (young/inexperienced)
#           32-47: Some skill
#           48-99: High skill
#           100+:  Gym Leaders, E4, Champion, highest level
module PBTrainerAI
  # Minimum skill level to be in each AI category
  def PBTrainerAI.minimumSkill; 1; end
  def PBTrainerAI.mediumSkill; 32; end
  def PBTrainerAI.highSkill; 48; end
  def PBTrainerAI.bestSkill; 100; end   # Gym Leaders, E4, Champion
end



class PokeBattle_Battle
################################################################################
# Get a score for each move being considered (trainer-owned Pokémon only).
# Moves with higher scores are more likely to be chosen.
################################################################################
  def pbGetMoveScore(move,attacker,opponent,skill=100)
    skill=PBTrainerAI.minimumSkill if skill<PBTrainerAI.minimumSkill
    score=100
    opponent=attacker.pbOppositeOpposing if !opponent
    opponent=opponent.pbPartner if opponent && opponent.fainted?
##### Alter score depending on the move's function code ########################
    case move.function
    when 0x00 # No extra effect
    when 0x01
      score-=95
      if skill>=PBTrainerAI.highSkill
        score=0
      end
    when 0x02 # Struggle
    when 0x03
      if opponent.pbCanSleep?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.mediumSkill
          score-=30 if opponent.effects[PBEffects::Yawn]>0
        end
        if skill>=PBTrainerAI.highSkill
          score-=30 if opponent.hasWorkingAbility(:MARVELSCALE)
        end
        if skill>=PBTrainerAI.bestSkill
          for i in opponent.moves
            movedata=PBMoveData.new(i.id)
            if movedata.function==0xB4 || # Sleep Talk
               movedata.function==0x11    # Snore
              score-=50
              break
            end
          end
        end
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=90 if move.basedamage==0
        end
      end
    when 0x04
      if opponent.effects[PBEffects::Yawn]>0 || !opponent.pbCanSleep?(attacker,false)
        if skill>=PBTrainerAI.mediumSkill
          score-=90
        end
      else
        score+=30
        if skill>=PBTrainerAI.highSkill
          score-=30 if opponent.hasWorkingAbility(:MARVELSCALE)
        end
        if skill>=PBTrainerAI.bestSkill
          for i in opponent.moves
            movedata=PBMoveData.new(i.id)
            if movedata.function==0xB4 || # Sleep Talk
               movedata.function==0x11    # Snore
              score-=50
              break
            end
          end
        end
      end
    when 0x05, 0x06, 0xBE
      if opponent.pbCanPoison?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.mediumSkill
          score+=30 if opponent.hp<=opponent.totalhp/4
          score+=50 if opponent.hp<=opponent.totalhp/8
          score-=40 if opponent.effects[PBEffects::Yawn]>0
        end
        if skill>=PBTrainerAI.highSkill
          score+=10 if pbRoughStat(opponent,PBStats::DEFENSE,skill)>100
          score+=10 if pbRoughStat(opponent,PBStats::SPDEF,skill)>100
          score-=40 if opponent.hasWorkingAbility(:GUTS)
          score-=40 if opponent.hasWorkingAbility(:MARVELSCALE)
          score-=40 if opponent.hasWorkingAbility(:TOXICBOOST)
        end
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=90 if move.basedamage==0
        end
      end
    when 0x07, 0x08, 0x09, 0xC5
      if opponent.pbCanParalyze?(attacker,false) &&
         !(skill>=PBTrainerAI.mediumSkill &&
         isConst?(move.id,PBMoves,:THUNDERWAVE) &&
         pbTypeModifier(move.type,attacker,opponent)==0)
        score+=30
        if skill>=PBTrainerAI.mediumSkill
           aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
           ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
          if aspeed<ospeed
            score+=30
          elsif aspeed>ospeed
            score-=40
          end
        end
        if skill>=PBTrainerAI.highSkill
          score-=40 if opponent.hasWorkingAbility(:GUTS)
          score-=40 if opponent.hasWorkingAbility(:MARVELSCALE)
          score-=40 if opponent.hasWorkingAbility(:QUICKFEET)
        end
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=90 if move.basedamage==0
        end
      end
    when 0x0A, 0x0B, 0xC6
      if opponent.pbCanBurn?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.highSkill
          score-=40 if opponent.hasWorkingAbility(:GUTS)
          score-=40 if opponent.hasWorkingAbility(:MARVELSCALE)
          score-=40 if opponent.hasWorkingAbility(:QUICKFEET)
          score-=40 if opponent.hasWorkingAbility(:FLAREBOOST)
        end
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=90 if move.basedamage==0
        end
      end
    when 0x0C, 0x0D, 0x0E
      if opponent.pbCanFreeze?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.highSkill
          score-=20 if opponent.hasWorkingAbility(:MARVELSCALE)
        end
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=90 if move.basedamage==0
        end
      end
    when 0x0F
      score+=30
      if skill>=PBTrainerAI.highSkill
        score+=30 if !opponent.hasWorkingAbility(:INNERFOCUS) &&
                     opponent.effects[PBEffects::Substitute]==0
      end
    when 0x10
      if skill>=PBTrainerAI.highSkill
        score+=30 if !opponent.hasWorkingAbility(:INNERFOCUS) &&
                     opponent.effects[PBEffects::Substitute]==0
      end
      score+=30 if opponent.effects[PBEffects::Minimize]
    when 0x11
      if attacker.status==PBStatuses::SLEEP
        score+=100 # Because it can be used while asleep
        if skill>=PBTrainerAI.highSkill
          score+=30 if !opponent.hasWorkingAbility(:INNERFOCUS) &&
                       opponent.effects[PBEffects::Substitute]==0
        end
      else
        score-=90 # Because it will fail here
        if skill>=PBTrainerAI.bestSkill
          score=0
        end
      end
    when 0x12
      if attacker.turncount==0
        if skill>=PBTrainerAI.highSkill
          score+=30 if !opponent.hasWorkingAbility(:INNERFOCUS) &&
                       opponent.effects[PBEffects::Substitute]==0
        end
      else
        score-=90 # Because it will fail here
        if skill>=PBTrainerAI.bestSkill
          score=0
        end
      end
    when 0x13, 0x14, 0x15
      if opponent.pbCanConfuse?(attacker,false)
        score+=30
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=90 if move.basedamage==0
        end
      end
    when 0x16
      canattract=true
      agender=attacker.gender
      ogender=opponent.gender
      if agender==2 || ogender==2 || agender==ogender
        score-=90; canattract=false
      elsif opponent.effects[PBEffects::Attract]>=0
        score-=80; canattract=false
      elsif skill>=PBTrainerAI.bestSkill &&
         opponent.hasWorkingAbility(:OBLIVIOUS)
        score-=80; canattract=false
      end
      if skill>=PBTrainerAI.highSkill
        if canattract && opponent.hasWorkingItem(:DESTINYKNOT) &&
           attacker.pbCanAttract?(opponent,false)
          score-=30
        end
      end
    when 0x17
      score+=30 if opponent.status==0
    when 0x18
      if attacker.status==PBStatuses::BURN
        score+=40
      elsif attacker.status==PBStatuses::POISON
        score+=40
        if skill>=PBTrainerAI.mediumSkill
          if attacker.hp<attacker.totalhp/8
            score+=60
          elsif skill>=PBTrainerAI.highSkill &&
             attacker.hp<(attacker.effects[PBEffects::Toxic]+1)*attacker.totalhp/16
            score+=60
          end
        end
      elsif attacker.status==PBStatuses::PARALYSIS
        score+=40
      else
        score-=90
      end
    when 0x19
      party=pbParty(attacker.index)
      statuses=0
      for i in 0...party.length
        statuses+=1 if party[i] && party[i].status!=0
      end
      if statuses==0
        score-=80
      else
        score+=20*statuses
      end
    when 0x1A
      if attacker.pbOwnSide.effects[PBEffects::Safeguard]>0
        score-=80 
      elsif attacker.status!=0
        score-=40
      else
        score+=30
      end
    when 0x1B
      if attacker.status==0
        score-=90
      else
        score+=40
      end
    when 0x1C
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::ATTACK)
          score-=90
        else
          score-=attacker.stages[PBStats::ATTACK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasphysicalattack=false
            for thismove in attacker.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsPhysical?(thismove.type)
                hasphysicalattack=true
              end
            end
            if hasphysicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=20 if attacker.stages[PBStats::ATTACK]<0
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          end
        end
      end
    when 0x1D, 0x1E, 0xC8
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::DEFENSE)
          score-=90
        else
          score-=attacker.stages[PBStats::DEFENSE]*20
        end
      else
        score+=20 if attacker.stages[PBStats::DEFENSE]<0
      end
    when 0x1F
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::SPEED)
          score-=90
        else
          score-=attacker.stages[PBStats::SPEED]*10
          if skill>=PBTrainerAI.highSkill
            aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
            ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
            if aspeed<ospeed && aspeed*2>ospeed
              score+=30
            end
          end
        end
      else
        score+=20 if attacker.stages[PBStats::SPEED]<0
      end
    when 0x20
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::SPATK)
          score-=90
        else
          score-=attacker.stages[PBStats::SPATK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasspecicalattack=false
            for thismove in attacker.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsSpecial?(thismove.type)
                hasspecicalattack=true
              end
            end
            if hasspecicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=20 if attacker.stages[PBStats::SPATK]<0
        if skill>=PBTrainerAI.mediumSkill
          hasspecicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecicalattack=true
            end
          end
          if hasspecicalattack
            score+=20
          end
        end
      end
    when 0x21
      foundmove=false
      for i in 0...4
        if isConst?(attacker.moves[i].type,PBTypes,:ELECTRIC) &&
           attacker.moves[i].basedamage>0
          foundmove=true
          break
        end
      end
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::SPDEF)
          score-=90
        else
          score-=attacker.stages[PBStats::SPDEF]*20
        end
        score+=20 if foundmove
      else
        score+=20 if attacker.stages[PBStats::SPDEF]<0
        score+=20 if foundmove
      end
    when 0x22
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::EVASION)
          score-=90
        else
          score-=attacker.stages[PBStats::EVASION]*10
        end
      else
        score+=20 if attacker.stages[PBStats::EVASION]<0
      end
    when 0x23
      if move.basedamage==0
        if attacker.effects[PBEffects::FocusEnergy]>=2
          score-=80
        else
          score+=30
        end
      else
        score+=30 if attacker.effects[PBEffects::FocusEnergy]<2
      end
    when 0x24
      if attacker.pbTooHigh?(PBStats::ATTACK) &&
         attacker.pbTooHigh?(PBStats::DEFENSE)
        score-=90
      else
        score-=attacker.stages[PBStats::ATTACK]*10
        score-=attacker.stages[PBStats::DEFENSE]*10
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
      end
    when 0x25
      if attacker.pbTooHigh?(PBStats::ATTACK) &&
         attacker.pbTooHigh?(PBStats::DEFENSE) &&
         attacker.pbTooHigh?(PBStats::ACCURACY)
        score-=90
      else
        score-=attacker.stages[PBStats::ATTACK]*10
        score-=attacker.stages[PBStats::DEFENSE]*10
        score-=attacker.stages[PBStats::ACCURACY]*10
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
      end
    when 0x26
      score+=40 if attacker.turncount==0 # Dragon Dance tends to be popular
      if attacker.pbTooHigh?(PBStats::ATTACK) &&
         attacker.pbTooHigh?(PBStats::SPEED)
        score-=90
      else
        score-=attacker.stages[PBStats::ATTACK]*10
        score-=attacker.stages[PBStats::SPEED]*10
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
        if skill>=PBTrainerAI.highSkill
          aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
          ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
          if aspeed<ospeed && aspeed*2>ospeed
            score+=20
          end
        end
      end
    when 0x27, 0x28
      if attacker.pbTooHigh?(PBStats::ATTACK) &&
         attacker.pbTooHigh?(PBStats::SPATK)
        score-=90
      else
        score-=attacker.stages[PBStats::ATTACK]*10
        score-=attacker.stages[PBStats::SPATK]*10
        if skill>=PBTrainerAI.mediumSkill
          hasdamagingattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0
              hasdamagingattack=true; break
            end
          end
          if hasdamagingattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
        if move.function==0x28 # Growth
          score+=20 if pbWeather==PBWeather::SUNNYDAY
        end
      end
    when 0x29
      if attacker.pbTooHigh?(PBStats::ATTACK) &&
         attacker.pbTooHigh?(PBStats::ACCURACY)
        score-=90
      else
        score-=attacker.stages[PBStats::ATTACK]*10
        score-=attacker.stages[PBStats::ACCURACY]*10
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
      end
    when 0x2A
      if attacker.pbTooHigh?(PBStats::DEFENSE) &&
         attacker.pbTooHigh?(PBStats::SPDEF)
        score-=90
      else
        score-=attacker.stages[PBStats::DEFENSE]*10
        score-=attacker.stages[PBStats::SPDEF]*10
      end
    when 0x2B
      if attacker.pbTooHigh?(PBStats::SPEED) &&
         attacker.pbTooHigh?(PBStats::SPATK) &&
         attacker.pbTooHigh?(PBStats::SPDEF)
        score-=90
      else
        score-=attacker.stages[PBStats::SPATK]*10
        score-=attacker.stages[PBStats::SPDEF]*10
        score-=attacker.stages[PBStats::SPEED]*10
        if skill>=PBTrainerAI.mediumSkill
          hasspecicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecicalattack=true
            end
          end
          if hasspecicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
        if skill>=PBTrainerAI.highSkill
          aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
          ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
          if aspeed<ospeed && aspeed*2>ospeed
            score+=20
          end
        end
      end
    when 0x2C
      if attacker.pbTooHigh?(PBStats::SPATK) &&
         attacker.pbTooHigh?(PBStats::SPDEF)
        score-=90
      else
        score+=40 if attacker.turncount==0 # Calm Mind tends to be popular
        score-=attacker.stages[PBStats::SPATK]*10
        score-=attacker.stages[PBStats::SPDEF]*10
        if skill>=PBTrainerAI.mediumSkill
          hasspecicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecicalattack=true
            end
          end
          if hasspecicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
      end
    when 0x2D
      score+=10 if attacker.stages[PBStats::ATTACK]<0
      score+=10 if attacker.stages[PBStats::DEFENSE]<0
      score+=10 if attacker.stages[PBStats::SPEED]<0
      score+=10 if attacker.stages[PBStats::SPATK]<0
      score+=10 if attacker.stages[PBStats::SPDEF]<0 
      if skill>=PBTrainerAI.mediumSkill
        hasdamagingattack=false
        for thismove in attacker.moves
          if thismove.id!=0 && thismove.basedamage>0
            hasdamagingattack=true
          end
        end
        if hasdamagingattack
          score+=20
        end
      end
    when 0x2E
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::ATTACK)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score-=attacker.stages[PBStats::ATTACK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasphysicalattack=false
            for thismove in attacker.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsPhysical?(thismove.type)
                hasphysicalattack=true
              end
            end
            if hasphysicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if attacker.stages[PBStats::ATTACK]<0
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          end
        end
      end
    when 0x2F
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::DEFENSE)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score-=attacker.stages[PBStats::DEFENSE]*20
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if attacker.stages[PBStats::DEFENSE]<0
      end
    when 0x30, 0x31
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::SPEED)
          score-=90
        else
          score+=20 if attacker.turncount==0
          score-=attacker.stages[PBStats::SPEED]*10
          if skill>=PBTrainerAI.highSkill
            aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
            ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
            if aspeed<ospeed && aspeed*2>ospeed
              score+=30
            end
          end
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if attacker.stages[PBStats::SPEED]<0
      end
    when 0x32
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::SPATK)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score-=attacker.stages[PBStats::SPATK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasspecicalattack=false
            for thismove in attacker.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsSpecial?(thismove.type)
                hasspecicalattack=true
              end
            end
            if hasspecicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if attacker.stages[PBStats::SPATK]<0
        if skill>=PBTrainerAI.mediumSkill
          hasspecicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecicalattack=true
            end
          end
          if hasspecicalattack
            score+=20
          end
        end
      end
    when 0x33
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::SPDEF)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score-=attacker.stages[PBStats::SPDEF]*20
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if attacker.stages[PBStats::SPDEF]<0
      end
    when 0x34
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::EVASION)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score-=attacker.stages[PBStats::EVASION]*10
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if attacker.stages[PBStats::EVASION]<0
      end
    when 0x35
      score-=attacker.stages[PBStats::ATTACK]*20
      score-=attacker.stages[PBStats::SPEED]*20
      score-=attacker.stages[PBStats::SPATK]*20
      score+=attacker.stages[PBStats::DEFENSE]*10
      score+=attacker.stages[PBStats::SPDEF]*10
      if skill>=PBTrainerAI.mediumSkill
        hasdamagingattack=false
        for thismove in attacker.moves
          if thismove.id!=0 && thismove.basedamage>0
            hasdamagingattack=true
          end
        end
        if hasdamagingattack
          score+=20
        end
      end
    when 0x36
      if attacker.pbTooHigh?(PBStats::ATTACK) &&
         attacker.pbTooHigh?(PBStats::SPEED)
        score-=90
      else
        score-=attacker.stages[PBStats::ATTACK]*10
        score-=attacker.stages[PBStats::SPEED]*10
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
        if skill>=PBTrainerAI.highSkill
          aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
          ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
          if aspeed<ospeed && aspeed*2>ospeed
            score+=30
          end
        end
      end
    when 0x37
      if opponent.pbTooHigh?(PBStats::ATTACK) &&
         opponent.pbTooHigh?(PBStats::DEFENSE) &&
         opponent.pbTooHigh?(PBStats::SPEED) &&
         opponent.pbTooHigh?(PBStats::SPATK) &&
         opponent.pbTooHigh?(PBStats::SPDEF) &&
         opponent.pbTooHigh?(PBStats::ACCURACY) &&
         opponent.pbTooHigh?(PBStats::EVASION)
        score-=90
      else
        avstat=0
        avstat-=opponent.stages[PBStats::ATTACK]
        avstat-=opponent.stages[PBStats::DEFENSE]
        avstat-=opponent.stages[PBStats::SPEED]
        avstat-=opponent.stages[PBStats::SPATK]
        avstat-=opponent.stages[PBStats::SPDEF]
        avstat-=opponent.stages[PBStats::ACCURACY]
        avstat-=opponent.stages[PBStats::EVASION]
        avstat=(avstat/2).floor if avstat<0 # More chance of getting even better
        score+=avstat*10
      end
    when 0x38
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::DEFENSE)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score-=attacker.stages[PBStats::DEFENSE]*30
        end
      else
        score+=10 if attacker.turncount==0
        score+=30 if attacker.stages[PBStats::DEFENSE]<0
      end
    when 0x39
      if move.basedamage==0
        if attacker.pbTooHigh?(PBStats::SPATK)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score-=attacker.stages[PBStats::SPATK]*30
          if skill>=PBTrainerAI.mediumSkill
            hasspecicalattack=false
            for thismove in attacker.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsSpecial?(thismove.type)
                hasspecicalattack=true
              end
            end
            if hasspecicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=10 if attacker.turncount==0
        score+=30 if attacker.stages[PBStats::SPATK]<0
        if skill>=PBTrainerAI.mediumSkill
          hasspecicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecicalattack=true
            end
          end
          if hasspecicalattack
            score+=30
          end
        end
      end
    when 0x3A
      if attacker.pbTooHigh?(PBStats::ATTACK) ||
         attacker.hp<=attacker.totalhp/2
        score-=100
      else
        score+=(6-attacker.stages[PBStats::ATTACK])*10
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=40
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
      end
    when 0x3B
      avg=attacker.stages[PBStats::ATTACK]*10
      avg+=attacker.stages[PBStats::DEFENSE]*10
      score+=avg/2
    when 0x3C
      avg=attacker.stages[PBStats::DEFENSE]*10
      avg+=attacker.stages[PBStats::SPDEF]*10
      score+=avg/2
    when 0x3D
      avg=attacker.stages[PBStats::DEFENSE]*10
      avg+=attacker.stages[PBStats::SPEED]*10
      avg+=attacker.stages[PBStats::SPDEF]*10
      score+=(avg/3).floor
    when 0x3E
      score+=attacker.stages[PBStats::SPEED]*10
    when 0x3F
      score+=attacker.stages[PBStats::SPATK]*10
    when 0x40
      if !opponent.pbCanConfuse?(attacker,false)
        score-=90
      else
        score+=30 if opponent.stages[PBStats::SPATK]<0
      end
    when 0x41
      if !opponent.pbCanConfuse?(attacker,false)
        score-=90
      else
        score+=30 if opponent.stages[PBStats::ATTACK]<0
      end
    when 0x42
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::ATTACK,attacker)
          score-=90
        else
          score+=opponent.stages[PBStats::ATTACK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasphysicalattack=false
            for thismove in opponent.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsPhysical?(thismove.type)
                hasphysicalattack=true
              end
            end
            if hasphysicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=20 if opponent.stages[PBStats::ATTACK]>0
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in opponent.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          end
        end
      end
    when 0x43
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::DEFENSE,attacker)
          score-=90
        else
          score+=opponent.stages[PBStats::DEFENSE]*20
        end
      else
        score+=20 if opponent.stages[PBStats::DEFENSE]>0
      end
    when 0x44
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::SPEED,attacker)
          score-=90
        else
          score+=opponent.stages[PBStats::SPEED]*10
          if skill>=PBTrainerAI.highSkill
            aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
            ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
            if aspeed<ospeed && aspeed*2>ospeed
              score+=30
            end
          end
        end
      else
        score+=20 if attacker.stages[PBStats::SPEED]>0
      end
    when 0x45
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::SPATK,attacker)
          score-=90
        else
          score+=attacker.stages[PBStats::SPATK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasspecicalattack=false
            for thismove in opponent.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsSpecial?(thismove.type)
                hasspecicalattack=true
              end
            end
            if hasspecicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=20 if attacker.stages[PBStats::SPATK]>0
        if skill>=PBTrainerAI.mediumSkill
          hasspecicalattack=false
          for thismove in opponent.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecicalattack=true
            end
          end
          if hasspecicalattack
            score+=20
          end
        end
      end
    when 0x46
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::SPDEF,attacker)
          score-=90
        else
          score+=opponent.stages[PBStats::SPDEF]*20
        end
      else
        score+=20 if opponent.stages[PBStats::SPDEF]>0
      end
    when 0x47
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::ACCURACY,attacker)
          score-=90
        else
          score+=opponent.stages[PBStats::ACCURACY]*10
        end
      else
        score+=20 if opponent.stages[PBStats::ACCURACY]>0
      end
    when 0x48
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::EVASION,attacker)
          score-=90
        else
          score+=opponent.stages[PBStats::EVASION]*10
        end
      else
        score+=20 if opponent.stages[PBStats::EVASION]>0
      end
    when 0x49
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::EVASION,attacker)
          score-=90
        else
          score+=opponent.stages[PBStats::EVASION]*10
        end
      else
        score+=20 if opponent.stages[PBStats::EVASION]>0
      end
      score+=30 if opponent.pbOwnSide.effects[PBEffects::Reflect]>0 ||
                   opponent.pbOwnSide.effects[PBEffects::LightScreen]>0 ||
                   opponent.pbOwnSide.effects[PBEffects::Mist]>0 ||
                   opponent.pbOwnSide.effects[PBEffects::Safeguard]>0
      score-=30 if opponent.pbOwnSide.effects[PBEffects::Spikes]>0 ||
                   opponent.pbOwnSide.effects[PBEffects::ToxicSpikes]>0 ||
                   opponent.pbOwnSide.effects[PBEffects::StealthRock]
    when 0x4A
      avg=opponent.stages[PBStats::ATTACK]*10
      avg+=opponent.stages[PBStats::DEFENSE]*10
      score+=avg/2
    when 0x4B
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::ATTACK,attacker)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score+=opponent.stages[PBStats::ATTACK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasphysicalattack=false
            for thismove in opponent.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsPhysical?(thismove.type)
                hasphysicalattack=true
              end
            end
            if hasphysicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if opponent.stages[PBStats::ATTACK]>0
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in opponent.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          end
        end
      end
    when 0x4C
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::DEFENSE,attacker)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score+=opponent.stages[PBStats::DEFENSE]*20
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if opponent.stages[PBStats::DEFENSE]>0
      end
    when 0x4D
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::SPEED,attacker)
          score-=90
        else
          score+=20 if attacker.turncount==0
          score+=opponent.stages[PBStats::SPEED]*20
          if skill>=PBTrainerAI.highSkill
            aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
            ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
            if aspeed<ospeed && aspeed*2>ospeed
              score+=30
            end
          end
        end
      else
        score+=10 if attacker.turncount==0
        score+=30 if opponent.stages[PBStats::SPEED]>0
      end
    when 0x4E
      if attacker.gender==2 || opponent.gender==2 ||
         attacker.gender==opponent.gender ||
         opponent.hasWorkingAbility(:OBLIVIOUS)
        score-=90
      elsif move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::SPATK,attacker)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score+=opponent.stages[PBStats::SPATK]*20
          if skill>=PBTrainerAI.mediumSkill
            hasspecicalattack=false
            for thismove in opponent.moves
              if thismove.id!=0 && thismove.basedamage>0 &&
                 thismove.pbIsSpecial?(thismove.type)
                hasspecicalattack=true
              end
            end
            if hasspecicalattack
              score+=20
            elsif skill>=PBTrainerAI.highSkill
              score-=90
            end
          end
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if opponent.stages[PBStats::SPATK]>0
        if skill>=PBTrainerAI.mediumSkill
          hasspecicalattack=false
          for thismove in opponent.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecicalattack=true
            end
          end
          if hasspecicalattack
            score+=30
          end
        end
      end
    when 0x4F
      if move.basedamage==0
        if !opponent.pbCanReduceStatStage?(PBStats::SPDEF,attacker)
          score-=90
        else
          score+=40 if attacker.turncount==0
          score+=opponent.stages[PBStats::SPDEF]*20
        end
      else
        score+=10 if attacker.turncount==0
        score+=20 if opponent.stages[PBStats::SPDEF]>0
      end
    when 0x50
      if opponent.effects[PBEffects::Substitute]>0
        score-=90
      else
        anychange=false
        avg=opponent.stages[PBStats::ATTACK]; anychange=true if avg!=0
        avg+=opponent.stages[PBStats::DEFENSE]; anychange=true if avg!=0
        avg+=opponent.stages[PBStats::SPEED]; anychange=true if avg!=0
        avg+=opponent.stages[PBStats::SPATK]; anychange=true if avg!=0
        avg+=opponent.stages[PBStats::SPDEF]; anychange=true if avg!=0
        avg+=opponent.stages[PBStats::ACCURACY]; anychange=true if avg!=0
        avg+=opponent.stages[PBStats::EVASION]; anychange=true if avg!=0
        if anychange
          score+=avg*10
        else
          score-=90
        end
      end
    when 0x51
      if skill>=PBTrainerAI.mediumSkill
        stages=0
        for i in 0...4
          battler=@battlers[i]
          if attacker.pbIsOpposing?(i)
            stages+=battler.stages[PBStats::ATTACK]
            stages+=battler.stages[PBStats::DEFENSE]
            stages+=battler.stages[PBStats::SPEED]
            stages+=battler.stages[PBStats::SPATK]
            stages+=battler.stages[PBStats::SPDEF]
            stages+=battler.stages[PBStats::EVASION]
            stages+=battler.stages[PBStats::ACCURACY]
          else
            stages-=battler.stages[PBStats::ATTACK]
            stages-=battler.stages[PBStats::DEFENSE]
            stages-=battler.stages[PBStats::SPEED]
            stages-=battler.stages[PBStats::SPATK]
            stages-=battler.stages[PBStats::SPDEF]
            stages-=battler.stages[PBStats::EVASION]
            stages-=battler.stages[PBStats::ACCURACY]
          end
        end
        score+=stages*10
      end
    when 0x52
      if skill>=PBTrainerAI.mediumSkill
        aatk=attacker.stages[PBStats::ATTACK]
        aspa=attacker.stages[PBStats::SPATK]
        oatk=opponent.stages[PBStats::ATTACK]
        ospa=opponent.stages[PBStats::SPATK]
        if aatk>=oatk && aspa>=ospa
          score-=80
        else
          score+=(oatk-aatk)*10
          score+=(ospa-aspa)*10
        end
      else
        score-=50
      end
    when 0x53
      if skill>=PBTrainerAI.mediumSkill
        adef=attacker.stages[PBStats::DEFENSE]
        aspd=attacker.stages[PBStats::SPDEF]
        odef=opponent.stages[PBStats::DEFENSE]
        ospd=opponent.stages[PBStats::SPDEF]
        if adef>=odef && aspd>=ospd
          score-=80
        else
          score+=(odef-adef)*10
          score+=(ospd-aspd)*10
        end
      else
        score-=50
      end
    when 0x54
      if skill>=PBTrainerAI.mediumSkill
        astages=attacker.stages[PBStats::ATTACK]
        astages+=attacker.stages[PBStats::DEFENSE]
        astages+=attacker.stages[PBStats::SPEED]
        astages+=attacker.stages[PBStats::SPATK]
        astages+=attacker.stages[PBStats::SPDEF]
        astages+=attacker.stages[PBStats::EVASION]
        astages+=attacker.stages[PBStats::ACCURACY]
        ostages=opponent.stages[PBStats::ATTACK]
        ostages+=opponent.stages[PBStats::DEFENSE]
        ostages+=opponent.stages[PBStats::SPEED]
        ostages+=opponent.stages[PBStats::SPATK]
        ostages+=opponent.stages[PBStats::SPDEF]
        ostages+=opponent.stages[PBStats::EVASION]
        ostages+=opponent.stages[PBStats::ACCURACY]
        score+=(ostages-astages)*10
      else
        score-=50
      end
    when 0x55
      if skill>=PBTrainerAI.mediumSkill
        equal=true
        for i in [PBStats::ATTACK,PBStats::DEFENSE,PBStats::SPEED,
                 PBStats::SPATK,PBStats::SPDEF,PBStats::ACCURACY,PBStats::EVASION]
          stagediff=opponent.stages[i]-attacker.stages[i]
          score+=stagediff*10
          equal=false if stagediff!=0
        end
        score-=80 if equal
      else
        score-=50
      end
    when 0x56
      score-=80 if attacker.pbOwnSide.effects[PBEffects::Mist]>0
    when 0x57
      if skill>=PBTrainerAI.mediumSkill
        aatk=pbRoughStat(attacker,PBStats::ATTACK,skill)
        adef=pbRoughStat(attacker,PBStats::DEFENSE,skill)
        if aatk==adef ||
           attacker.effects[PBEffects::PowerTrick] # No flip-flopping
          score-=90
        elsif adef>aatk # Prefer a higher Attack
          score+=30
        else
          score-=30
        end
      else
        score-=30
      end
    when 0x58
      if skill>=PBTrainerAI.mediumSkill
        aatk=pbRoughStat(attacker,PBStats::ATTACK,skill)
        aspatk=pbRoughStat(attacker,PBStats::SPATK,skill)
        oatk=pbRoughStat(opponent,PBStats::ATTACK,skill)
        ospatk=pbRoughStat(opponent,PBStats::SPATK,skill)
        if aatk<oatk && aspatk<ospatk
          score+=50
        elsif (aatk+aspatk)<(oatk+ospatk)
          score+=30
        else
          score-=50
        end
      else
        score-=30
      end
    when 0x59
      if skill>=PBTrainerAI.mediumSkill
        adef=pbRoughStat(attacker,PBStats::DEFENSE,skill)
        aspdef=pbRoughStat(attacker,PBStats::SPDEF,skill)
        odef=pbRoughStat(opponent,PBStats::DEFENSE,skill)
        ospdef=pbRoughStat(opponent,PBStats::SPDEF,skill)
        if adef<odef && aspdef<ospdef
          score+=50
        elsif (adef+aspdef)<(odef+ospdef)
          score+=30
        else
          score-=50
        end
      else
        score-=30
      end
    when 0x5A
      if opponent.effects[PBEffects::Substitute]>0
        score-=90
      elsif attacker.hp>=(attacker.hp+opponent.hp)/2
        score-=90
      else
        score+=40
      end
    when 0x5B
      if attacker.pbOwnSide.effects[PBEffects::Tailwind]>0
        score-=90
      end
    when 0x5C
      blacklist=[
         0x02,   # Struggle
         0x14,   # Chatter
         0x5C,   # Mimic
         0x5D,   # Sketch
         0xB6    # Metronome
      ]
      if attacker.effects[PBEffects::Transform] ||
         opponent.lastMoveUsed<=0 ||
         isConst?(PBMoveData.new(opponent.lastMoveUsed).type,PBTypes,:SHADOW) ||
         blacklist.include?(PBMoveData.new(opponent.lastMoveUsed).function)
        score-=90
      end
      for i in attacker.moves
        if i.id==opponent.lastMoveUsed
          score-=90; break
        end
      end
    when 0x5D
      blacklist=[
         0x02,   # Struggle
         0x14,   # Chatter
         0x5D    # Sketch
      ]
      if attacker.effects[PBEffects::Transform] ||
         opponent.lastMoveUsedSketch<=0 ||
         isConst?(PBMoveData.new(opponent.lastMoveUsedSketch).type,PBTypes,:SHADOW) ||
         blacklist.include?(PBMoveData.new(opponent.lastMoveUsedSketch).function)
        score-=90
      end
      for i in attacker.moves
        if i.id==opponent.lastMoveUsedSketch
          score-=90; break
        end
      end
    when 0x5E
      if isConst?(attacker.ability,PBAbilities,:MULTITYPE)
        score-=90
      else
        types=[]
        for i in attacker.moves
          next if i.id==@id
          next if PBTypes.isPseudoType?(i.type)
          next if attacker.pbHasType?(i.type)
          found=false
          types.push(i.type) if !types.include?(i.type)
        end
        if types.length==0
          score-=90
        end
      end
    when 0x5F
      if isConst?(attacker.ability,PBAbilities,:MULTITYPE)
        score-=90
      elsif opponent.lastMoveUsed<=0 ||
         PBTypes.isPseudoType?(PBMoveData.new(opponent.lastMoveUsed).type)
        score-=90
      else
        atype=-1
        for i in opponent.moves
          if i.id==opponent.lastMoveUsed
            atype=i.pbType(move.type,attacker,opponent); break
          end
        end
        if atype<0
          score-=90
        else
          types=[]
          for i in 0..PBTypes.maxValue
            next if attacker.pbHasType?(i)
            types.push(i) if PBTypes.getEffectiveness(atype,i)<2 
          end
          if types.length==0
            score-=90
          end
        end
      end
    when 0x60
      if isConst?(attacker.ability,PBAbilities,:MULTITYPE)
        score-=90
      elsif skill>=PBTrainerAI.mediumSkill
        envtypes=[
           :NORMAL, # None
           :GRASS,  # Grass
           :GRASS,  # Tall grass
           :WATER,  # Moving water
           :WATER,  # Still water
           :WATER,  # Underwater
           :ROCK,   # Rock
           :ROCK,   # Cave
           :GROUND  # Sand
        ]
        type=envtypes[@environment]
        score-=90 if attacker.pbHasType?(type)
      end
    when 0x61
      if opponent.effects[PBEffects::Substitute]>0 ||
         isConst?(opponent.ability,PBAbilities,:MULTITYPE)
        score-=90
      elsif opponent.pbHasType?(:WATER)
        score-=90
      end
    when 0x62
      if isConst?(attacker.ability,PBAbilities,:MULTITYPE)
        score-=90
      elsif attacker.pbHasType?(opponent.type1) &&
         attacker.pbHasType?(opponent.type2) &&
         opponent.pbHasType?(attacker.type1) &&
         opponent.pbHasType?(attacker.type2)
        score-=90
      end
    when 0x63
      if opponent.effects[PBEffects::Substitute]>0
        score-=90
      elsif skill>=PBTrainerAI.mediumSkill
        if isConst?(opponent.ability,PBAbilities,:MULTITYPE) ||
           isConst?(opponent.ability,PBAbilities,:SIMPLE) ||
           isConst?(opponent.ability,PBAbilities,:TRUANT)
          score-=90
        end
      end
    when 0x64
      if opponent.effects[PBEffects::Substitute]>0
        score-=90
      elsif skill>=PBTrainerAI.mediumSkill
        if isConst?(opponent.ability,PBAbilities,:MULTITYPE) ||
           isConst?(opponent.ability,PBAbilities,:INSOMNIA) ||
           isConst?(opponent.ability,PBAbilities,:TRUANT)
          score-=90
        end
      end
    when 0x65
      score-=40 # don't prefer this move
      if skill>=PBTrainerAI.mediumSkill
        if opponent.ability==0 ||
           attacker.ability==opponent.ability ||
           isConst?(attacker.ability,PBAbilities,:MULTITYPE) ||
           isConst?(opponent.ability,PBAbilities,:FLOWERGIFT) ||
           isConst?(opponent.ability,PBAbilities,:FORECAST) ||
           isConst?(opponent.ability,PBAbilities,:ILLUSION) ||
           isConst?(opponent.ability,PBAbilities,:IMPOSTER) ||
           isConst?(opponent.ability,PBAbilities,:MULTITYPE) ||
           isConst?(opponent.ability,PBAbilities,:TRACE) ||
           isConst?(opponent.ability,PBAbilities,:WONDERGUARD) ||
           isConst?(opponent.ability,PBAbilities,:ZENMODE)
          score-=90
        end
      end
      if skill>=PBTrainerAI.highSkill
        if isConst?(opponent.ability,PBAbilities,:TRUANT) && 
           attacker.pbIsOpposing?(opponent.index)
          score-=90
        elsif isConst?(opponent.ability,PBAbilities,:SLOWSTART) &&
           attacker.pbIsOpposing?(opponent.index)
          score-=90
        end
      end
    when 0x66
      score-=40 # don't prefer this move
      if opponent.effects[PBEffects::Substitute]>0
        score-=90
      elsif skill>=PBTrainerAI.mediumSkill
        if attacker.ability==0 ||
           attacker.ability==opponent.ability ||
           isConst?(opponent.ability,PBAbilities,:MULTITYPE) ||
           isConst?(opponent.ability,PBAbilities,:TRUANT) ||
           isConst?(attacker.ability,PBAbilities,:FLOWERGIFT) ||
           isConst?(attacker.ability,PBAbilities,:FORECAST) ||
           isConst?(attacker.ability,PBAbilities,:ILLUSION) ||
           isConst?(attacker.ability,PBAbilities,:IMPOSTER) ||
           isConst?(attacker.ability,PBAbilities,:MULTITYPE) ||
           isConst?(attacker.ability,PBAbilities,:TRACE) ||
           isConst?(attacker.ability,PBAbilities,:ZENMODE)
          score-=90
        end
        if skill>=PBTrainerAI.highSkill
          if isConst?(attacker.ability,PBAbilities,:TRUANT) && 
             attacker.pbIsOpposing?(opponent.index)
            score+=90
          elsif isConst?(attacker.ability,PBAbilities,:SLOWSTART) &&
             attacker.pbIsOpposing?(opponent.index)
            score+=90
          end
        end
      end
    when 0x67
      score-=40 # don't prefer this move
      if skill>=PBTrainerAI.mediumSkill
        if (attacker.ability==0 && opponent.ability==0) ||
           attacker.ability==opponent.ability ||
           isConst?(attacker.ability,PBAbilities,:ILLUSION) ||
           isConst?(opponent.ability,PBAbilities,:ILLUSION) ||
           isConst?(attacker.ability,PBAbilities,:MULTITYPE) ||
           isConst?(opponent.ability,PBAbilities,:MULTITYPE) ||
           isConst?(attacker.ability,PBAbilities,:WONDERGUARD) ||
           isConst?(opponent.ability,PBAbilities,:WONDERGUARD)
          score-=90
        end
      end
      if skill>=PBTrainerAI.highSkill
        if isConst?(opponent.ability,PBAbilities,:TRUANT) && 
           attacker.pbIsOpposing?(opponent.index)
          score-=90
        elsif isConst?(opponent.ability,PBAbilities,:SLOWSTART) &&
          attacker.pbIsOpposing?(opponent.index)
          score-=90
        end
      end
    when 0x68
      if opponent.effects[PBEffects::Substitute]>0 ||
         opponent.effects[PBEffects::GastroAcid]
        score-=90
      elsif skill>=PBTrainerAI.highSkill
        score-=90 if isConst?(opponent.ability,PBAbilities,:MULTITYPE)
        score-=90 if isConst?(opponent.ability,PBAbilities,:SLOWSTART)
        score-=90 if isConst?(opponent.ability,PBAbilities,:TRUANT)
      end
    when 0x69
      score-=70
    when 0x6A
      if opponent.hp<=20
        score+=80
      elsif opponent.level>=25
        score-=80 # Not useful against high-level Pokemon
      end
    when 0x6B
      score+=80 if opponent.hp<=40
    when 0x6C
      score-=50
      score+=(opponent.hp*100/opponent.totalhp).floor
    when 0x6D
      score+=80 if opponent.hp<=attacker.level
    when 0x6E
      if attacker.hp>=opponent.hp
        score-=90
      elsif attacker.hp*2<opponent.hp
        score+=50
      end
    when 0x6F
      score+=30 if opponent.hp<=attacker.level
    when 0x70
      score-=90 if opponent.hasWorkingAbility(:STURDY)
      score-=90 if opponent.level>attacker.level
    when 0x71
      if opponent.effects[PBEffects::HyperBeam]>0
        score-=90
      else
        attack=pbRoughStat(attacker,PBStats::ATTACK,skill)
        spatk=pbRoughStat(attacker,PBStats::SPATK,skill)
        if attack*1.5<spatk
          score-=60
        elsif skill>=PBTrainerAI.mediumSkill &&
           opponent.lastMoveUsed>0
          moveData=PBMoveData.new(opponent.lastMoveUsed)
          if moveData.basedamage>0 &&
             (USEMOVECATEGORY && moveData.category==2) ||
             (!USEMOVECATEGORY && PBTypes.isSpecialType?(moveData.type))
            score-=60
          end
        end
      end
    when 0x72
      if opponent.effects[PBEffects::HyperBeam]>0
        score-=90
      else
        attack=pbRoughStat(attacker,PBStats::ATTACK,skill)
        spatk=pbRoughStat(attacker,PBStats::SPATK,skill)
        if attack>spatk*1.5
          score-=60
        elsif skill>=PBTrainerAI.mediumSkill && opponent.lastMoveUsed>0
          moveData=PBMoveData.new(opponent.lastMoveUsed)
          if moveData.basedamage>0 &&
             (USEMOVECATEGORY && moveData.category==1) ||
             (!USEMOVECATEGORY && !PBTypes.isSpecialType?(moveData.type))
            score-=60
          end
        end
      end
    when 0x73
      score-=90 if opponent.effects[PBEffects::HyperBeam]>0
    when 0x74
      score+=10 if !opponent.pbPartner.fainted?
    when 0x75
    when 0x76
    when 0x77
    when 0x78
      if skill>=PBTrainerAI.highSkill
        score+=30 if !opponent.hasWorkingAbility(:INNERFOCUS) &&
                     opponent.effects[PBEffects::Substitute]==0
      end
    when 0x79
    when 0x7A
    when 0x7B
    when 0x7C
      score-=20 if opponent.status==PBStatuses::PARALYSIS # Will cure status
    when 0x7D
      score-=20 if opponent.status==PBStatuses::SLEEP && # Will cure status
                   opponent.statusCount>1
    when 0x7E
    when 0x7F
    when 0x80
    when 0x81
      attspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
      oppspeed=pbRoughStat(opponent,PBStats::SPEED,skill)
      score+=30 if oppspeed>attspeed
    when 0x82
      score+=20 if @doublebattle
    when 0x83
      if skill>=PBTrainerAI.mediumSkill
        score+=20 if @doublebattle && !attacker.pbPartner.fainted? &&
                     attacker.pbPartner.pbHasMove?(move.id)
      end
    when 0x84
      attspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
      oppspeed=pbRoughStat(opponent,PBStats::SPEED,skill)
      score+=30 if oppspeed>attspeed
    when 0x85
    when 0x86
    when 0x87
    when 0x88
    when 0x89
    when 0x8A
    when 0x8B
    when 0x8C
    when 0x8D
    when 0x8E
    when 0x8F
    when 0x90
    when 0x91
    when 0x92
    when 0x93
      score+=25 if attacker.effects[PBEffects::Rage]
    when 0x94
    when 0x95
    when 0x96
      score-=90 if !pbIsBerry?(attacker.item)
    when 0x97
    when 0x98
    when 0x99
    when 0x9A
    when 0x9B
    when 0x9C
      score-=90 if attacker.pbPartner.fainted?
    when 0x9D
      score-=90 if attacker.effects[PBEffects::MudSport]
    when 0x9E
      score-=90 if attacker.effects[PBEffects::WaterSport]
    when 0x9F
    when 0xA0
    when 0xA1
      score-=90 if attacker.pbOwnSide.effects[PBEffects::LuckyChant]>0
    when 0xA2
      score-=90 if attacker.pbOwnSide.effects[PBEffects::Reflect]>0
    when 0xA3
      score-=90 if attacker.pbOwnSide.effects[PBEffects::LightScreen]>0
    when 0xA4
    when 0xA5
    when 0xA6
      score-=90 if opponent.effects[PBEffects::Substitute]>0
      score-=90 if opponent.effects[PBEffects::LockOn]>0
    when 0xA7
      if opponent.effects[PBEffects::Foresight]
        score-=90
      elsif opponent.pbHasType?(:GHOST)
        score+=70
      elsif opponent.stages[PBStats::EVASION]<=0
        score-=60
      end
    when 0xA8
      if opponent.effects[PBEffects::MiracleEye]
        score-=90
      elsif opponent.pbHasType?(:DARK)
        score+=70
      elsif opponent.stages[PBStats::EVASION]<=0
        score-=60
      end
    when 0xA9
    when 0xAA
      if attacker.effects[PBEffects::ProtectRate]>1 ||
         opponent.effects[PBEffects::HyperBeam]>0
        score-=90
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=(attacker.effects[PBEffects::ProtectRate]*40)
        end
        score+=50 if attacker.turncount==0
        score+=30 if opponent.effects[PBEffects::TwoTurnAttack]!=0
      end
    when 0xAB
    when 0xAC
    when 0xAD
    when 0xAE
      score-=40
      if skill>=PBTrainerAI.highSkill
        score-=100 if opponent.lastMoveUsed<=0 ||
                     (PBMoveData.new(opponent.lastMoveUsed).flags&0x10)==0 # flag e: Copyable by Mirror Move
      end
    when 0xAF
    when 0xB0
    when 0xB1
    when 0xB2
    when 0xB3
    when 0xB4
      if attacker.status==PBStatuses::SLEEP
        score+=200 # Because it can be used while asleep
      else
        score-=80
      end
    when 0xB5
    when 0xB6
    when 0xB7
      score-=90 if opponent.effects[PBEffects::Torment]
    when 0xB8
      score-=90 if attacker.effects[PBEffects::Imprison]
    when 0xB9
      score-=90 if opponent.effects[PBEffects::Disable]>0 
    when 0xBA
      score-=90 if opponent.effects[PBEffects::Taunt]>0
    when 0xBB
      score-=90 if opponent.effects[PBEffects::HealBlock]>0
    when 0xBC
      aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
      ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
      if opponent.effects[PBEffects::Encore]>0
        score-=90
      elsif aspeed>ospeed
        if opponent.lastMoveUsed<=0
          score-=90
        else
          moveData=PBMoveData.new(opponent.lastMoveUsed)
          if moveData.basedamage==0 && (moveData.target==0x10 || moveData.target==0x20)
            score+=60
          elsif moveData.basedamage!=0 && moveData.target==0x00 &&
             pbTypeModifier(moveData.type,opponent,attacker)==0
            score+=60
          end
        end
      end
    when 0xBD
    when 0xBF
    when 0xC0
    when 0xC1
    when 0xC2
    when 0xC3
    when 0xC4
    when 0xC7
      score+=20 if attacker.effects[PBEffects::FocusEnergy]>0
      if skill>=PBTrainerAI.highSkill
        score+=20 if !opponent.hasWorkingAbility(:INNERFOCUS) &&
                     opponent.effects[PBEffects::Substitute]==0
      end
    when 0xC9
    when 0xCA
    when 0xCB
    when 0xCC
    when 0xCD
    when 0xCE
    when 0xCF
      score+=40 if opponent.effects[PBEffects::MultiTurn]==0
    when 0xD0
      score+=40 if opponent.effects[PBEffects::MultiTurn]==0
    when 0xD1
    when 0xD2
    when 0xD3
    when 0xD4
      if attacker.hp<=attacker.totalhp/4
        score-=90 
      elsif attacker.hp<=attacker.totalhp/2
        score-=50 
      end
    when 0xD5, 0xD6
      if attacker.hp==attacker.totalhp
        score-=90
      else
        score+=50
        score-=(attacker.hp*100/attacker.totalhp)
      end
    when 0xD7
      score-=90 if attacker.effects[PBEffects::Wish]>0
    when 0xD8
      if attacker.hp==attacker.totalhp
        score-=90
      else
        case pbWeather
        when PBWeather::SUNNYDAY
          score+=30
        when PBWeather::RAINDANCE, PBWeather::SANDSTORM, PBWeather::HAIL
          score-=30
        end
        score+=50
        score-=(attacker.hp*100/attacker.totalhp)
      end
    when 0xD9
      if attacker.hp==attacker.totalhp || !attacker.pbCanSleep?(attacker,false,nil,true)
        score-=90
      else
        score+=70
        score-=(attacker.hp*140/attacker.totalhp)
        score+=30 if attacker.status!=0
      end
    when 0xDA
      score-=90 if attacker.effects[PBEffects::AquaRing]
    when 0xDB
      score-=90 if attacker.effects[PBEffects::Ingrain]
    when 0xDC
      if opponent.effects[PBEffects::LeechSeed]>=0
        score-=90
      elsif skill>=PBTrainerAI.mediumSkill && opponent.pbHasType?(:GRASS)
        score-=90
      else
        score+=60 if attacker.turncount==0
      end
    when 0xDD
      if skill>=PBTrainerAI.highSkill && opponent.hasWorkingAbility(:LIQUIDOOZE)
        score-=70
      else
        score+=20 if attacker.hp<=(attacker.totalhp/2)
      end
    when 0xDE
      if opponent.status!=PBStatuses::SLEEP
        score-=100
      elsif skill>=PBTrainerAI.highSkill && opponent.hasWorkingAbility(:LIQUIDOOZE)
        score-=70
      else
        score+=20 if attacker.hp<=(attacker.totalhp/2)
      end
    when 0xDF
      if attacker.pbIsOpposing?(opponent.index)
        score-=100
      else
        score+=20 if opponent.hp<(opponent.totalhp/2) &&
                     opponent.effects[PBEffects::Substitute]==0
      end
    when 0xE0
      reserves=attacker.pbNonActivePokemonCount
      foes=attacker.pbOppositeOpposing.pbNonActivePokemonCount
      if pbCheckGlobalAbility(:DAMP)
        score-=100
      elsif skill>=PBTrainerAI.mediumSkill && reserves==0 && foes>0
        score-=100 # don't want to lose
      elsif skill>=PBTrainerAI.highSkill && reserves==0 && foes==0
        score-=100 # don't want to draw
      else
        score-=(attacker.hp*100/attacker.totalhp)
      end
    when 0xE1
    when 0xE2
      if !opponent.pbCanReduceStatStage?(PBStats::ATTACK,attacker) &&
         !opponent.pbCanReduceStatStage?(PBStats::SPATK,attacker)
        score-=100
      elsif attacker.pbNonActivePokemonCount()==0
        score-=100 
      else
        score+=(opponent.stages[PBStats::ATTACK]*10)
        score+=(opponent.stages[PBStats::SPATK]*10)
        score-=(attacker.hp*100/attacker.totalhp)
      end
    when 0xE3, 0xE4
      score-=70
    when 0xE5
      if attacker.pbNonActivePokemonCount()==0
        score-=90
      else
        score-=90 if opponent.effects[PBEffects::PerishSong]>0
      end
    when 0xE6
      score+=50
      score-=(attacker.hp*100/attacker.totalhp)
      score+=30 if attacker.hp<=(attacker.totalhp/10)
    when 0xE7
      score+=50
      score-=(attacker.hp*100/attacker.totalhp)
      score+=30 if attacker.hp<=(attacker.totalhp/10)
    when 0xE8
      score-=25 if attacker.hp>(attacker.totalhp/2)
      if skill>=PBTrainerAI.mediumSkill
        score-=90 if attacker.effects[PBEffects::ProtectRate]>1
        score-=90 if opponent.effects[PBEffects::HyperBeam]>0
      else
        score-=(attacker.effects[PBEffects::ProtectRate]*40)
      end
    when 0xE9
      if opponent.hp==1
        score-=90
      elsif opponent.hp<=(opponent.totalhp/8)
        score-=60
      elsif opponent.hp<=(opponent.totalhp/4)
        score-=30
      end
    when 0xEA
      score-=100 if @opponent
    when 0xEB
      if opponent.effects[PBEffects::Ingrain] ||
         (skill>=PBTrainerAI.highSkill && opponent.hasWorkingAbility(:SUCTIONCUPS))
        score-=90 
      else
        party=pbParty(opponent.index)
        ch=0
        for i in 0...party.length
          ch+=1 if pbCanSwitchLax?(opponent.index,i,false)
        end
        score-=90 if ch==0
      end
      if score>20
        score+=50 if opponent.pbOwnSide.effects[PBEffects::Spikes]>0
        score+=50 if opponent.pbOwnSide.effects[PBEffects::ToxicSpikes]>0
        score+=50 if opponent.pbOwnSide.effects[PBEffects::StealthRock]
      end
    when 0xEC
      if !opponent.effects[PBEffects::Ingrain] &&
         !(skill>=PBTrainerAI.highSkill && opponent.hasWorkingAbility(:SUCTIONCUPS))
        score+=40 if opponent.pbOwnSide.effects[PBEffects::Spikes]>0
        score+=40 if opponent.pbOwnSide.effects[PBEffects::ToxicSpikes]>0
        score+=40 if opponent.pbOwnSide.effects[PBEffects::StealthRock]
      end
    when 0xED
      if !pbCanChooseNonActive?(attacker.index)
        score-=80
      else
        score-=40 if attacker.effects[PBEffects::Confusion]>0
        total=0
        total+=(attacker.stages[PBStats::ATTACK]*10)
        total+=(attacker.stages[PBStats::DEFENSE]*10)
        total+=(attacker.stages[PBStats::SPEED]*10)
        total+=(attacker.stages[PBStats::SPATK]*10)
        total+=(attacker.stages[PBStats::SPDEF]*10)
        total+=(attacker.stages[PBStats::EVASION]*10)
        total+=(attacker.stages[PBStats::ACCURACY]*10)
        if total<=0 || attacker.turncount==0
          score-=60
        else
          score+=total
          # special case: attacker has no damaging moves
          hasDamagingMove=false
          for m in attacker.moves
            if move.id!=0 && move.basedamage>0
              hasDamagingMove=true
            end
          end
          if !hasDamagingMove
            score+=75
          end
        end
      end
    when 0xEE
    when 0xEF
      score-=90 if opponent.effects[PBEffects::MeanLook]>=0
    when 0xF0
      if skill>=PBTrainerAI.highSkill
        score+=20 if opponent.item!=0
      end
    when 0xF1
      if skill>=PBTrainerAI.highSkill
        if attacker.item==0 && opponent.item!=0
          score+=40
        else
          score-=90
        end
      else
        score-=80
      end
    when 0xF2
      if attacker.item==0 && opponent.item==0
        score-=90
      elsif skill>=PBTrainerAI.highSkill && opponent.hasWorkingAbility(:STICKYHOLD)
        score-=90
      elsif attacker.hasWorkingItem(:FLAMEORB) ||
            attacker.hasWorkingItem(:TOXICORB) ||
            attacker.hasWorkingItem(:STICKYBARB) ||
            attacker.hasWorkingItem(:IRONBALL) ||
            attacker.hasWorkingItem(:CHOICEBAND) ||
            attacker.hasWorkingItem(:CHOICESCARF) ||
            attacker.hasWorkingItem(:CHOICESPECS)
        score+=50
      elsif attacker.item==0 && opponent.item!=0
        score-=30 if PBMoveData.new(attacker.lastMoveUsed).function==0xF2 # Trick/Switcheroo
      end
    when 0xF3
      if attacker.item==0 || opponent.item!=0
        score-=90
      else
        if attacker.hasWorkingItem(:FLAMEORB) ||
           attacker.hasWorkingItem(:TOXICORB) ||
           attacker.hasWorkingItem(:STICKYBARB) ||
           attacker.hasWorkingItem(:IRONBALL) ||
           attacker.hasWorkingItem(:CHOICEBAND) ||
           attacker.hasWorkingItem(:CHOICESCARF) ||
           attacker.hasWorkingItem(:CHOICESPECS)
          score+=50
        else
          score-=80
        end
      end
    when 0xF4, 0xF5
      if opponent.effects[PBEffects::Substitute]==0
        if skill>=PBTrainerAI.highSkill && pbIsBerry?(opponent.item)
          score+=30
        end
      end
    when 0xF6
      if attacker.pokemon.itemRecycle==0 || attacker.item!=0
        score-=80
      elsif attacker.pokemon.itemRecycle!=0
        score+=30
      end
    when 0xF7
      if attacker.item==0 ||
         pbIsUnlosableItem(attacker,attacker.item) ||
         pbIsPokeBall?(attacker.item) ||
         attacker.hasWorkingAbility(:KLUTZ) ||
         attacker.effects[PBEffects::Embargo]>0
        score-=90
      end
    when 0xF8
      score-=90 if opponent.effects[PBEffects::Embargo]>0
    when 0xF9
      if @field.effects[PBEffects::MagicRoom]>0
        score-=90
      else
        score+=30 if attacker.item==0 && opponent.item!=0
      end
    when 0xFA
      score-=25
    when 0xFB
      score-=30
    when 0xFC
      score-=40
    when 0xFD
      score-=30
      if opponent.pbCanParalyze?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.mediumSkill
           aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
           ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
          if aspeed<ospeed
            score+=30
          elsif aspeed>ospeed
            score-=40
          end
        end
        if skill>=PBTrainerAI.highSkill
          score-=40 if opponent.hasWorkingAbility(:GUTS)
          score-=40 if opponent.hasWorkingAbility(:MARVELSCALE)
          score-=40 if opponent.hasWorkingAbility(:QUICKFEET)
        end
      end
    when 0xFE
      score-=30
      if opponent.pbCanBurn?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.highSkill
          score-=40 if opponent.hasWorkingAbility(:GUTS)
          score-=40 if opponent.hasWorkingAbility(:MARVELSCALE)
          score-=40 if opponent.hasWorkingAbility(:QUICKFEET)
          score-=40 if opponent.hasWorkingAbility(:FLAREBOOST)
        end
      end
    when 0xFF
      if pbCheckGlobalAbility(:AIRLOCK) ||
         pbCheckGlobalAbility(:CLOUDNINE)
        score-=90
      elsif pbWeather==PBWeather::SUNNYDAY
        score-=90
      else
        for move in attacker.moves
          if move.id!=0 && move.basedamage>0 &&
             isConst?(move.type,PBTypes,:FIRE)
            score+=20
          end
        end
      end
    when 0x100
      if pbCheckGlobalAbility(:AIRLOCK) ||
         pbCheckGlobalAbility(:CLOUDNINE)
        score-=90
      elsif pbWeather==PBWeather::RAINDANCE
        score-=90
      else
        for move in attacker.moves
          if move.id!=0 && move.basedamage>0 &&
             isConst?(move.type,PBTypes,:WATER)
            score+=20
          end
        end
      end
    when 0x101
      if pbCheckGlobalAbility(:AIRLOCK) ||
         pbCheckGlobalAbility(:CLOUDNINE)
        score-=90
      elsif pbWeather==PBWeather::SANDSTORM
        score-=90
      end
    when 0x102
      if pbCheckGlobalAbility(:AIRLOCK) ||
         pbCheckGlobalAbility(:CLOUDNINE)
        score-=90
      elsif pbWeather==PBWeather::HAIL
        score-=90
      end
    when 0x103
      if attacker.pbOpposingSide.effects[PBEffects::Spikes]>=3
        score-=90
      elsif !pbCanChooseNonActive?(attacker.pbOpposing1.index) &&
            !pbCanChooseNonActive?(attacker.pbOpposing2.index)
        # Opponent can't switch in any Pokemon
        score-=90
      else
        score+=5*attacker.pbOppositeOpposing.pbNonActivePokemonCount()
        score+=[40,26,13][attacker.pbOpposingSide.effects[PBEffects::Spikes]]
      end
    when 0x104
      if attacker.pbOpposingSide.effects[PBEffects::ToxicSpikes]>=2
        score-=90
      elsif !pbCanChooseNonActive?(attacker.pbOpposing1.index) &&
            !pbCanChooseNonActive?(attacker.pbOpposing2.index)
        # Opponent can't switch in any Pokemon
        score-=90
      else
        score+=4*attacker.pbOppositeOpposing.pbNonActivePokemonCount()
        score+=[26,13][attacker.pbOpposingSide.effects[PBEffects::ToxicSpikes]]
      end
    when 0x105
      if attacker.pbOpposingSide.effects[PBEffects::StealthRock]
        score-=90
      elsif !pbCanChooseNonActive?(attacker.pbOpposing1.index) &&
            !pbCanChooseNonActive?(attacker.pbOpposing2.index)
        # Opponent can't switch in any Pokemon
        score-=90
      else
        score+=5*attacker.pbOppositeOpposing.pbNonActivePokemonCount()
      end
    when 0x106
    when 0x107
    when 0x108
    when 0x109
    when 0x10A
      score+=20 if attacker.pbOpposingSide.effects[PBEffects::Reflect]>0
      score+=20 if attacker.pbOpposingSide.effects[PBEffects::LightScreen]>0
    when 0x10B
      score+=10*(attacker.stages[PBStats::ACCURACY]-opponent.stages[PBStats::EVASION])
    when 0x10C
      if attacker.effects[PBEffects::Substitute]>0
        score-=90
      elsif attacker.hp<=(attacker.totalhp/4)
        score-=90
      end
    when 0x10D
      if attacker.pbHasType?(:GHOST)
        if opponent.effects[PBEffects::Curse]
          score-=90
        elsif attacker.hp<=(attacker.totalhp/2)
          if attacker.pbNonActivePokemonCount()==0
            score-=90
          else
            score-=50
            score-=30 if @shiftStyle
          end
        end
      else
        avg=(attacker.stages[PBStats::SPEED]*10)
        avg-=(attacker.stages[PBStats::ATTACK]*10)
        avg-=(attacker.stages[PBStats::DEFENSE]*10)
        score+=avg/3
      end
    when 0x10E
      score-=40
    when 0x10F
      if opponent.effects[PBEffects::Nightmare] ||
         opponent.effects[PBEffects::Substitute]>0
        score-=90
      elsif opponent.status!=PBStatuses::SLEEP
        score-=90
      else
        score-=90 if opponent.statusCount<=1
        score+=50 if opponent.statusCount>3
      end
    when 0x110
      score+=30 if attacker.effects[PBEffects::MultiTurn]>0
      score+=30 if attacker.effects[PBEffects::LeechSeed]>=0
      if attacker.pbNonActivePokemonCount()>0
        score+=80 if attacker.pbOwnSide.effects[PBEffects::Spikes]>0
        score+=80 if attacker.pbOwnSide.effects[PBEffects::ToxicSpikes]>0
        score+=80 if attacker.pbOwnSide.effects[PBEffects::StealthRock]
      end
    when 0x111
      if opponent.effects[PBEffects::FutureSight]>0
        score-=100
      elsif attacker.pbNonActivePokemonCount()==0
        # Future Sight tends to be wasteful if down to last Pokemon
        score-=70
      end
    when 0x112
      avg=0
      avg-=(attacker.stages[PBStats::DEFENSE]*10)
      avg-=(attacker.stages[PBStats::SPDEF]*10)
      score+=avg/2
      if attacker.effects[PBEffects::Stockpile]>=3
        score-=80
      else
        # More preferable if user also has Spit Up/Swallow
        for move in attacker.moves
          if move.function==0x113 || move.function==0x114 # Spit Up, Swallow
            score+=20; break
          end
        end
      end
    when 0x113
      score-=100 if attacker.effects[PBEffects::Stockpile]==0
    when 0x114
      if attacker.effects[PBEffects::Stockpile]==0
        score-=90
      elsif attacker.hp==attacker.totalhp
        score-=90
      else
        mult=[0,25,50,100][attacker.effects[PBEffects::Stockpile]]
        score+=mult
        score-=(attacker.hp*mult*2/attacker.totalhp)
      end
    when 0x115
      score+=50 if opponent.effects[PBEffects::HyperBeam]>0
      score-=35 if opponent.hp<=(opponent.totalhp/2) # If opponent is weak, no
      score-=70 if opponent.hp<=(opponent.totalhp/4) # need to risk this move
    when 0x116
    when 0x117
      if !@doublebattle
        score-=100
      elsif attacker.pbPartner.fainted?
        score-=90
      end
    when 0x118
      if @field.effects[PBEffects::Gravity]>0
        score-=90
      elsif skill>=PBTrainerAI.mediumSkill
        score-=30
        score-=20 if attacker.effects[PBEffects::SkyDrop]
        score-=20 if attacker.effects[PBEffects::MagnetRise]>0
        score-=20 if attacker.effects[PBEffects::Telekinesis]>0
        score-=20 if attacker.pbHasType?(:FLYING)
        score-=20 if attacker.hasWorkingAbility(:LEVITATE)
        score-=20 if attacker.hasWorkingItem(:AIRBALLOON)
        score+=20 if opponent.effects[PBEffects::SkyDrop]
        score+=20 if opponent.effects[PBEffects::MagnetRise]>0
        score+=20 if opponent.effects[PBEffects::Telekinesis]>0
        score+=20 if PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xC9 || # Fly
                     PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCC || # Bounce
                     PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCE    # Sky Drop
        score+=20 if opponent.pbHasType?(:FLYING)
        score+=20 if opponent.hasWorkingAbility(:LEVITATE)
        score+=20 if opponent.hasWorkingItem(:AIRBALLOON)
      end
    when 0x119
      if attacker.effects[PBEffects::MagnetRise]>0 ||
         attacker.effects[PBEffects::Ingrain] ||
         attacker.effects[PBEffects::SmackDown]
        score-=90
      end
    when 0x11A
      if opponent.effects[PBEffects::Telekinesis]>0 ||
         opponent.effects[PBEffects::Ingrain] ||
         opponent.effects[PBEffects::SmackDown]
        score-=90
      end
    when 0x11B
    when 0x11C
      if skill>=PBTrainerAI.mediumSkill
        score+=20 if opponent.effects[PBEffects::MagnetRise]>0
        score+=20 if opponent.effects[PBEffects::Telekinesis]>0
        score+=20 if PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xC9 || # Fly
                     PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCC    # Bounce
        score+=20 if opponent.pbHasType?(:FLYING)
        score+=20 if opponent.hasWorkingAbility(:LEVITATE)
        score+=20 if opponent.hasWorkingItem(:AIRBALLOON)
      end
    when 0x11D
    when 0x11E
    when 0x11F
    when 0x120
    when 0x121
    when 0x122
    when 0x123
      if !opponent.pbHasType?(attacker.type1) &&
         !opponent.pbHasType?(attacker.type2)
        score-=90
      end
    when 0x124
    when 0x125
    when 0x126
      score+=20 # Shadow moves are more preferable
    when 0x127
      score+=20 # Shadow moves are more preferable
      if opponent.pbCanParalyze?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.mediumSkill
           aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
           ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
          if aspeed<ospeed
            score+=30
          elsif aspeed>ospeed
            score-=40
          end
        end
        if skill>=PBTrainerAI.highSkill
          score-=40 if opponent.hasWorkingAbility(:GUTS)
          score-=40 if opponent.hasWorkingAbility(:MARVELSCALE)
          score-=40 if opponent.hasWorkingAbility(:QUICKFEET)
        end
      end
    when 0x128
      score+=20 # Shadow moves are more preferable
      if opponent.pbCanBurn?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.highSkill
          score-=40 if opponent.hasWorkingAbility(:GUTS)
          score-=40 if opponent.hasWorkingAbility(:MARVELSCALE)
          score-=40 if opponent.hasWorkingAbility(:QUICKFEET)
          score-=40 if opponent.hasWorkingAbility(:FLAREBOOST)
        end
      end
    when 0x129
      score+=20 # Shadow moves are more preferable
      if opponent.pbCanFreeze?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.highSkill
          score-=20 if opponent.hasWorkingAbility(:MARVELSCALE)
        end
      end
    when 0x12A
      score+=20 # Shadow moves are more preferable
      if opponent.pbCanConfuse?(attacker,false)
        score+=30
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=90
        end
      end
    when 0x12B
      score+=20 # Shadow moves are more preferable
      if !opponent.pbCanReduceStatStage?(PBStats::DEFENSE,attacker)
        score-=90
      else
        score+=40 if attacker.turncount==0
        score+=opponent.stages[PBStats::DEFENSE]*20
      end
    when 0x12C
      score+=20 # Shadow moves are more preferable
      if !opponent.pbCanReduceStatStage?(PBStats::EVASION,attacker)
        score-=90
      else
        score+=opponent.stages[PBStats::EVASION]*15
      end
    when 0x12D
      score+=20 # Shadow moves are more preferable
    when 0x12E
      score+=20 # Shadow moves are more preferable
      score+=20 if opponent.hp>=(opponent.totalhp/2)
      score-=20 if attacker.hp<(attacker.hp/2)
    when 0x12F
      score+=20 # Shadow moves are more preferable
      score-=110 if opponent.effects[PBEffects::MeanLook]>=0
    when 0x130
      score+=20 # Shadow moves are more preferable
      score-=40
    when 0x131
      score+=20 # Shadow moves are more preferable
      if pbCheckGlobalAbility(:AIRLOCK) ||
         pbCheckGlobalAbility(:CLOUDNINE)
        score-=90
      elsif pbWeather==PBWeather::SHADOWSKY
        score-=90
      end
    when 0x132
      score+=20 # Shadow moves are more preferable
      if opponent.pbOwnSide.effects[PBEffects::Reflect]>0 ||
         opponent.pbOwnSide.effects[PBEffects::LightScreen]>0 ||
         opponent.pbOwnSide.effects[PBEffects::Safeguard]>0
        score+=30
        score-=90 if attacker.pbOwnSide.effects[PBEffects::Reflect]>0 ||
                     attacker.pbOwnSide.effects[PBEffects::LightScreen]>0 ||
                     attacker.pbOwnSide.effects[PBEffects::Safeguard]>0
      else
        score-=110
      end
    when 0x133, 0x134
      score-=95
      if skill>=PBTrainerAI.highSkill
        score=0
      end
    when 0x135
      if opponent.pbCanFreeze?(attacker,false)
        score+=30
        if skill>=PBTrainerAI.highSkill
          score-=20 if opponent.hasWorkingAbility(:MARVELSCALE)
        end
      end
    when 0x136
      score+=20 if attacker.stages[PBStats::DEFENSE]<0
    when 0x137
      if attacker.pbTooHigh?(PBStats::DEFENSE) &&
         attacker.pbTooHigh?(PBStats::SPDEF) &&
         !attacker.pbPartner.fainted? &&
         attacker.pbPartner.pbTooHigh?(PBStats::DEFENSE) &&
         attacker.pbPartner.pbTooHigh?(PBStats::SPDEF)
        score-=90
      else
        score-=attacker.stages[PBStats::DEFENSE]*10
        score-=attacker.stages[PBStats::SPDEF]*10
        if !attacker.pbPartner.fainted?
          score-=attacker.pbPartner.stages[PBStats::DEFENSE]*10
          score-=attacker.pbPartner.stages[PBStats::SPDEF]*10
        end
      end
    when 0x138
      if !@doublebattle
        score-=100
      elsif attacker.pbPartner.fainted?
        score-=90
      else
        score-=attacker.pbPartner.stages[PBStats::SPDEF]*10
      end
    when 0x139
      if !opponent.pbCanReduceStatStage?(PBStats::ATTACK,attacker)
        score-=90
      else
        score+=opponent.stages[PBStats::ATTACK]*20
        if skill>=PBTrainerAI.mediumSkill
          hasphysicalattack=false
          for thismove in opponent.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsPhysical?(thismove.type)
              hasphysicalattack=true
            end
          end
          if hasphysicalattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
      end
    when 0x13A
      avg=opponent.stages[PBStats::ATTACK]*10
      avg+=opponent.stages[PBStats::SPATK]*10
      score+=avg/2
    when 0x13B
      if !isConst?(attacker.species,PBSpecies,:HOOPA) || attacker.form!=1
        score-=100
      else
        score+=20 if opponent.stages[PBStats::DEFENSE]>0
      end
    when 0x13C
      score+=20 if opponent.stages[PBStats::SPATK]>0
    when 0x13D
      if !opponent.pbCanReduceStatStage?(PBStats::SPATK,attacker)
        score-=90
      else
        score+=40 if attacker.turncount==0
        score+=opponent.stages[PBStats::SPATK]*20
      end
    when 0x13E
      count=0
      for i in 0...4
        battler=@battlers[i]
        if battler.pbHasType?(:GRASS) && !battler.isAirborne? &&
           (!battler.pbTooHigh?(PBStats::ATTACK) || !battler.pbTooHigh?(PBStats::SPATK))
          count+=1
          if attacker.pbIsOpposing?(battler)
            score-=20
          else
            score-=attacker.stages[PBStats::ATTACK]*10
            score-=attacker.stages[PBStats::SPATK]*10
          end
        end
      end
      score-=95 if count==0
    when 0x13F
      count=0
      for i in 0...4
        battler=@battlers[i]
        if battler.pbHasType?(:GRASS) && !battler.pbTooHigh?(PBStats::DEFENSE)
          count+=1
          if attacker.pbIsOpposing?(battler)
            score-=20
          else
            score-=attacker.stages[PBStats::DEFENSE]*10
          end
        end
      end
      score-=95 if count==0
    when 0x140
      count=0
      for i in 0...4
        battler=@battlers[i]
        if battler.status==PBStatuses::POISON &&
           (!battler.pbTooLow?(PBStats::ATTACK) ||
           !battler.pbTooLow?(PBStats::SPATK) ||
           !battler.pbTooLow?(PBStats::SPEED))
          count+=1
          if attacker.pbIsOpposing?(battler)
            score+=attacker.stages[PBStats::ATTACK]*10
            score+=attacker.stages[PBStats::SPATK]*10
            score+=attacker.stages[PBStats::SPEED]*10
          else
            score-=20
          end
        end
      end
      score-=95 if count==0
    when 0x141
      if opponent.effects[PBEffects::Substitute]>0
        score-=90
      else
        numpos=0; numneg=0
        for i in [PBStats::ATTACK,PBStats::DEFENSE,PBStats::SPEED,
                  PBStats::SPATK,PBStats::SPDEF,PBStats::ACCURACY,PBStats::EVASION]
          stat=opponent.stages[i]
          (stat>0) ? numpos+=stat : numneg+=stat
        end
        if numpos!=0 || numneg!=0
          score+=(numpos-numneg)*10
        else
          score-=95
        end
      end
    when 0x142
      if opponent.pbHasType?(:GHOST)
        score-=90
      end
    when 0x143
      if opponent.pbHasType?(:GRASS)
        score-=90
      end
    when 0x144
    when 0x145
      aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
      ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
      if aspeed>ospeed
        score-=90
      end
    when 0x146
    when 0x147
    when 0x148
      aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
      ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
      if aspeed>ospeed
        score-=90
      else
        score+=30 if opponent.pbHasMoveType?(:FIRE)
      end
    when 0x149
      if attacker.turncount==0
        score+=30
      else
        score-=90 # Because it will fail here
        score=0 if skill>=PBTrainerAI.bestSkill
      end
    when 0x14A
    when 0x14B, 0x14C
      if attacker.effects[PBEffects::ProtectRate]>1 ||
         opponent.effects[PBEffects::HyperBeam]>0
        score-=90
      else
        if skill>=PBTrainerAI.mediumSkill
          score-=(attacker.effects[PBEffects::ProtectRate]*40)
        end
        score+=50 if attacker.turncount==0
        score+=30 if opponent.effects[PBEffects::TwoTurnAttack]!=0
      end
    when 0x14D
    when 0x14E
      if attacker.pbTooHigh?(PBStats::SPATK) &&
         attacker.pbTooHigh?(PBStats::SPDEF) &&
         attacker.pbTooHigh?(PBStats::SPEED)
        score-=90
      else
        score-=attacker.stages[PBStats::SPATK]*10 # Only *10 isntead of *20
        score-=attacker.stages[PBStats::SPDEF]*10 # because two-turn attack
        score-=attacker.stages[PBStats::SPEED]*10
        if skill>=PBTrainerAI.mediumSkill
          hasspecialattack=false
          for thismove in attacker.moves
            if thismove.id!=0 && thismove.basedamage>0 &&
               thismove.pbIsSpecial?(thismove.type)
              hasspecialattack=true
            end
          end
          if hasspecialattack
            score+=20
          elsif skill>=PBTrainerAI.highSkill
            score-=90
          end
        end
        if skill>=PBTrainerAI.highSkill
          aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
          ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
          if aspeed<ospeed && aspeed*2>ospeed
            score+=30
          end
        end
      end
    when 0x14F
      if skill>=PBTrainerAI.highSkill && opponent.hasWorkingAbility(:LIQUIDOOZE)
        score-=80
      else
        score+=40 if attacker.hp<=(attacker.totalhp/2)
      end
    when 0x150
      score+=20 if !attacker.pbTooHigh?(PBStats::ATTACK) && opponent.hp<=(opponent.totalhp/4)
    when 0x151
      avg=opponent.stages[PBStats::ATTACK]*10
      avg+=opponent.stages[PBStats::SPATK]*10
      score+=avg/2
    when 0x152
    when 0x153
      score-=95 if opponent.pbOwnSide.effects[PBEffects::StickyWeb]
    when 0x154
    when 0x155
    when 0x156
    when 0x157
      score-=90
    when 0x158
      score-=90 if !attacker.pokemon || !attacker.pokemon.belch
    end
    # A score of 0 here means it should absolutely not be used
    return score if score<=0
##### Other score modifications ################################################
    # Prefer damaging moves if AI has no more Pokémon
    if attacker.pbNonActivePokemonCount==0
      if skill>=PBTrainerAI.mediumSkill &&
         !(skill>=PBTrainerAI.highSkill && opponent.pbNonActivePokemonCount>0)
        if move.basedamage==0
          score/=1.5
        elsif opponent.hp<=opponent.totalhp/2
          score*=1.5
        end
      end
    end
    # Don't prefer attacking the opponent if they'd be semi-invulnerable
    if opponent.effects[PBEffects::TwoTurnAttack]>0 &&
       skill>=PBTrainerAI.highSkill
      invulmove=PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function
      if move.accuracy>0 &&   # Checks accuracy, i.e. targets opponent
         ([0xC9,0xCA,0xCB,0xCC,0xCD,0xCE].include?(invulmove) ||
         opponent.effects[PBEffects::SkyDrop]) &&
         attacker.pbSpeed>opponent.pbSpeed
        if skill>=PBTrainerAI.bestSkill   # Can get past semi-invulnerability
          miss=false
          case invulmove
          when 0xC9, 0xCC # Fly, Bounce
            miss=true unless move.function==0x08 ||  # Thunder
                             move.function==0x15 ||  # Hurricane
                             move.function==0x77 ||  # Gust
                             move.function==0x78 ||  # Twister
                             move.function==0x11B || # Sky Uppercut
                             move.function==0x11C || # Smack Down
                             isConst?(move.id,PBMoves,:WHIRLWIND)
          when 0xCA # Dig
            miss=true unless move.function==0x76 || # Earthquake
                             move.function==0x95    # Magnitude
          when 0xCB # Dive
            miss=true unless move.function==0x75 || # Surf
                             move.function==0xD0    # Whirlpool
          when 0xCD # Shadow Force
            miss=true
          when 0xCE # Sky Drop
            miss=true unless move.function==0x08 ||  # Thunder
                             move.function==0x15 ||  # Hurricane
                             move.function==0x77 ||  # Gust
                             move.function==0x78 ||  # Twister
                             move.function==0x11B || # Sky Uppercut
                             move.function==0x11C    # Smack Down
          when 0x14D # Phantom Force
            miss=true
          end
          if opponent.effects[PBEffects::SkyDrop]
            miss=true unless move.function==0x08 ||  # Thunder
                             move.function==0x15 ||  # Hurricane
                             move.function==0x77 ||  # Gust
                             move.function==0x78 ||  # Twister
                             move.function==0x11B || # Sky Uppercut
                             move.function==0x11C    # Smack Down
          end
          score-=80 if miss
        else
          score-=80
        end
      end
    end
    # Pick a good move for the Choice items
    if attacker.hasWorkingItem(:CHOICEBAND) ||
       attacker.hasWorkingItem(:CHOICESPECS) ||
       attacker.hasWorkingItem(:CHOICESCARF)
      if skill>=PBTrainerAI.mediumSkill
        if move.basedamage>=60
          score+=60
        elsif move.basedamage>0
          score+=30
        elsif move.function==0xF2 # Trick
          score+=70
        else
          score-=60
        end
      end
    end
    # If user has King's Rock, prefer moves that may cause flinching with it # TODO
    # If user is asleep, prefer moves that are usable while asleep
    if attacker.status==PBStatuses::SLEEP
      if skill>=PBTrainerAI.mediumSkill
        if move.function!=0x11 && move.function!=0xB4 # Snore, Sleep Talk
          hasSleepMove=false
          for m in attacker.moves
            if m.function==0x11 || m.function==0xB4 # Snore, Sleep Talk
              hasSleepMove=true; break
            end
          end
          score-=60 if hasSleepMove
        end
      end
    end
    # If user is frozen, prefer a move that can thaw the user
    if attacker.status==PBStatuses::FROZEN
      if skill>=PBTrainerAI.mediumSkill
        if move.canThawUser?
          score+=40
        else
          hasFreezeMove=false
          for m in attacker.moves
            if m.canThawUser?
              hasFreezeMove=true; break
            end
          end
          score-=60 if hasFreezeMove
        end
      end
    end
    # If target is frozen, don't prefer moves that could thaw them # TODO
    # Adjust score based on how much damage it can deal
    if move.basedamage>0
      typemod=pbTypeModifier(move.type,attacker,opponent)
      if typemod==0 || score<=0
        score=0
      elsif skill>=PBTrainerAI.mediumSkill && typemod<=8 &&
            opponent.hasWorkingAbility(:WONDERGUARD)
        score=0
      elsif skill>=PBTrainerAI.mediumSkill && isConst?(move.type,PBTypes,:GROUND) &&
            (opponent.hasWorkingAbility(:LEVITATE) ||
            opponent.effects[PBEffects::MagnetRise]>0)
        score=0
      elsif skill>=PBTrainerAI.mediumSkill && isConst?(move.type,PBTypes,:FIRE) &&
            opponent.hasWorkingAbility(:FLASHFIRE)
        score=0
      elsif skill>=PBTrainerAI.mediumSkill && isConst?(move.type,PBTypes,:WATER) &&
            (opponent.hasWorkingAbility(:WATERABSORB) ||
            opponent.hasWorkingAbility(:STORMDRAIN) ||
            opponent.hasWorkingAbility(:DRYSKIN))
        score=0
      elsif skill>=PBTrainerAI.mediumSkill && isConst?(move.type,PBTypes,:GRASS) &&
            opponent.hasWorkingAbility(:SAPSIPPER)
        score=0
      elsif skill>=PBTrainerAI.mediumSkill && isConst?(move.type,PBTypes,:ELECTRIC) &&
            (opponent.hasWorkingAbility(:VOLTABSORB) ||
            opponent.hasWorkingAbility(:LIGHTNINGROD) ||
            opponent.hasWorkingAbility(:MOTORDRIVE))
        score=0
      else
        # Calculate how much damage the move will do (roughly)
        realDamage=move.basedamage
        realDamage=60 if move.basedamage==1
        if skill>=PBTrainerAI.mediumSkill
          realDamage=pbBetterBaseDamage(move,attacker,opponent,skill,realDamage)
        end
        realDamage=pbRoughDamage(move,attacker,opponent,skill,realDamage)
        # Account for accuracy of move
        accuracy=pbRoughAccuracy(move,attacker,opponent,skill)
        basedamage=realDamage*accuracy/100.0
        # Two-turn attacks waste 2 turns to deal one lot of damage
        if move.pbTwoTurnAttack(attacker) || move.function==0xC2 # Hyper Beam
          basedamage*=2/3   # Not halved because semi-invulnerable during use or hits first turn
        end
        # Prefer flinching effects
        if !opponent.hasWorkingAbility(:INNERFOCUS) &&
           opponent.effects[PBEffects::Substitute]==0
          if (attacker.hasWorkingItem(:KINGSROCK) || attacker.hasWorkingItem(:RAZORFANG)) &&
             move.canKingsRock?
            basedamage*=1.05
          elsif attacker.hasWorkingAbility(:STENCH) &&
                move.function!=0x09 && # Thunder Fang
                move.function!=0x0B && # Fire Fang
                move.function!=0x0E && # Ice Fang
                move.function!=0x0F && # flinch-inducing moves
                move.function!=0x10 && # Stomp
                move.function!=0x11 && # Snore
                move.function!=0x12 && # Fake Out
                move.function!=0x78 && # Twister
                move.function!=0xC7    # Sky Attack
            basedamage*=1.05
          end
        end
        # Convert damage to proportion of opponent's remaining HP
        basedamage=(basedamage*100.0/opponent.hp)
        # Don't prefer weak attacks
#        basedamage/=2 if basedamage<40
        # Prefer damaging attack if level difference is significantly high
        basedamage*=1.2 if attacker.level-10>opponent.level
        # Adjust score
        basedamage=basedamage.round
        basedamage=120 if basedamage>120   # Treat all OHKO moves the same
        basedamage+=40 if basedamage>100   # Prefer moves likely to OHKO
        score=score.round
        oldscore=score
        score+=basedamage
        PBDebug.log("[AI] #{PBMoves.getName(move.id)} damage calculated (#{realDamage}=>#{basedamage}% of target's #{opponent.hp} HP), score change #{oldscore}=>#{score}")
      end
    else
      # Don't prefer attacks which don't deal damage
      score-=10
      # Account for accuracy of move
      accuracy=pbRoughAccuracy(move,attacker,opponent,skill)
      score*=accuracy/100.0
      score=0 if score<=10 && skill>=PBTrainerAI.highSkill
    end
    score=score.to_i
    score=0 if score<0
    return score
  end

################################################################################
# Get type effectiveness and approximate stats.
################################################################################
  def pbTypeModifier(type,attacker,opponent)
    return 8 if type<0
    return 8 if isConst?(type,PBTypes,:GROUND) && opponent.pbHasType?(:FLYING) &&
                opponent.hasWorkingItem(:IRONBALL) && !USENEWBATTLEMECHANICS
    atype=type
    otype1=opponent.type1
    otype2=opponent.type2
    otype3=opponent.effects[PBEffects::Type3] || -1
    # Roost
    if isConst?(otype1,PBTypes,:FLYING) && opponent.effects[PBEffects::Roost]
      if isConst?(otype2,PBTypes,:FLYING) && isConst?(otype3,PBTypes,:FLYING)
        otype1=getConst(PBTypes,:NORMAL) || 0
      else
        otype1=otype2
      end
    end
    if isConst?(otype2,PBTypes,:FLYING) && opponent.effects[PBEffects::Roost]
      otype2=otype1
    end
    # Get effectivenesses
    mod1=PBTypes.getEffectiveness(atype,otype1)
    mod2=(otype1==otype2) ? 2 : PBTypes.getEffectiveness(atype,otype2)
    mod3=(otype3<0 || otype1==otype3 || otype2==otype3) ? 2 : PBTypes.getEffectiveness(atype,otype3)
    if opponent.hasWorkingItem(:RINGTARGET)
      mod1=2 if mod1==0
      mod2=2 if mod2==0
      mod3=2 if mod3==0
    end
    # Foresight
    if (attacker.hasWorkingAbility(:SCRAPPY) rescue false) || opponent.effects[PBEffects::Foresight]
      mod1=2 if isConst?(otype1,PBTypes,:GHOST) && PBTypes.isIneffective?(atype,otype1)
      mod2=2 if isConst?(otype2,PBTypes,:GHOST) && PBTypes.isIneffective?(atype,otype2)
      mod3=2 if isConst?(otype3,PBTypes,:GHOST) && PBTypes.isIneffective?(atype,otype3)
    end
    # Miracle Eye
    if opponent.effects[PBEffects::MiracleEye]
      mod1=2 if isConst?(otype1,PBTypes,:DARK) && PBTypes.isIneffective?(atype,otype1)
      mod2=2 if isConst?(otype2,PBTypes,:DARK) && PBTypes.isIneffective?(atype,otype2)
      mod3=2 if isConst?(otype3,PBTypes,:DARK) && PBTypes.isIneffective?(atype,otype3)
    end
    # Delta Stream's weather
    if pbWeather==PBWeather::STRONGWINDS
      mod1=2 if isConst?(otype1,PBTypes,:FLYING) && PBTypes.isSuperEffective?(atype,otype1)
      mod2=2 if isConst?(otype2,PBTypes,:FLYING) && PBTypes.isSuperEffective?(atype,otype2)
      mod3=2 if isConst?(otype3,PBTypes,:FLYING) && PBTypes.isSuperEffective?(atype,otype3)
    end
    # Smack Down makes Ground moves work against fliers
    if !opponent.isAirborne?((attacker.hasMoldBreaker rescue false)) && isConst?(atype,PBTypes,:GROUND)
      mod1=2 if isConst?(otype1,PBTypes,:FLYING)
      mod2=2 if isConst?(otype2,PBTypes,:FLYING)
      mod3=2 if isConst?(otype3,PBTypes,:FLYING)
    end
    return mod1*mod2*mod3
  end

  def pbTypeModifier2(battlerThis,battlerOther)
    # battlerThis isn't a Battler object, it's a Pokémon - it has no third type
    if battlerThis.type1==battlerThis.type2
      return 4*pbTypeModifier(battlerThis.type1,battlerThis,battlerOther)
    end
    ret=pbTypeModifier(battlerThis.type1,battlerThis,battlerOther)
    ret*=pbTypeModifier(battlerThis.type2,battlerThis,battlerOther)
    return ret*2 # 0,1,2,4,_8_,16,32,64
  end

  def pbRoughStat(battler,stat,skill)
    return battler.pbSpeed if skill>=PBTrainerAI.highSkill && stat==PBStats::SPEED
    stagemul=[10,10,10,10,10,10,10,15,20,25,30,35,40]
    stagediv=[40,35,30,25,20,15,10,10,10,10,10,10,10]
    stage=battler.stages[stat]+6
    value=0
    case stat
    when PBStats::ATTACK; value=battler.attack
    when PBStats::DEFENSE; value=battler.defense
    when PBStats::SPEED; value=battler.speed
    when PBStats::SPATK; value=battler.spatk
    when PBStats::SPDEF; value=battler.spdef
    end
    return (value*1.0*stagemul[stage]/stagediv[stage]).floor
  end

  def pbBetterBaseDamage(move,attacker,opponent,skill,basedamage)
    # Covers all function codes which have their own def pbBaseDamage
    case move.function
    when 0x6A # SonicBoom
      basedamage=20
    when 0x6B # Dragon Rage
      basedamage=40
    when 0x6C # Super Fang
      basedamage=(opponent.hp/2).floor
    when 0x6D # Night Shade
      basedamage=attacker.level
    when 0x6E # Endeavor
      basedamage=opponent.hp-attacker.hp
    when 0x6F # Psywave
      basedamage=attacker.level
    when 0x70 # OHKO
      basedamage=opponent.totalhp
    when 0x71 # Counter
      basedamage=60
    when 0x72 # Mirror Coat
      basedamage=60
    when 0x73 # Metal Burst
      basedamage=60
    when 0x75, 0x12D # Surf, Shadow Storm
      basedamage*=2 if PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCB # Dive
    when 0x76 # Earthquake
      basedamage*=2 if PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCA # Dig
    when 0x77, 0x78 # Gust, Twister
      basedamage*=2 if PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xC9 || # Fly
                       PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCC || # Bounce
                       PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCE    # Sky Drop
    when 0x7B # Venoshock
      basedamage*=2 if opponent.status==PBStatuses::POISON
    when 0x7C # SmellingSalt
      basedamage*=2 if opponent.status==PBStatuses::PARALYSIS
    when 0x7D # Wake-Up Slap
      basedamage*=2 if opponent.status==PBStatuses::SLEEP
    when 0x7E # Facade
      basedamage*=2 if attacker.status==PBStatuses::POISON ||
                       attacker.status==PBStatuses::BURN ||
                       attacker.status==PBStatuses::PARALYSIS
    when 0x7F # Hex
      basedamage*=2 if opponent.status!=0
    when 0x80 # Brine
      basedamage*=2 if opponent.hp<=(opponent.totalhp/2).floor
    when 0x85 # Retaliate
      # TODO
    when 0x86 # Acrobatics
      basedamage*=2 if attacker.item==0 || attacker.hasWorkingItem(:FLYINGGEM)
    when 0x87 # Weather Ball
      basedamage*=2 if pbWeather!=0
    when 0x89 # Return
      basedamage=[(attacker.happiness*2/5).floor,1].max
    when 0x8A # Frustration
      basedamage=[((255-attacker.happiness)*2/5).floor,1].max
    when 0x8B # Eruption
      basedamage=[(150*attacker.hp/attacker.totalhp).floor,1].max
    when 0x8C # Crush Grip
      basedamage=[(120*opponent.hp/opponent.totalhp).floor,1].max
    when 0x8D # Gyro Ball
      ospeed=pbRoughStat(opponent,PBStats::SPEED,skill)
      aspeed=pbRoughStat(attacker,PBStats::SPEED,skill)
      basedamage=[[(25*ospeed/aspeed).floor,150].min,1].max
    when 0x8E # Stored Power
      mult=0
      for i in [PBStats::ATTACK,PBStats::DEFENSE,PBStats::SPEED,
                PBStats::SPATK,PBStats::SPDEF,PBStats::ACCURACY,PBStats::EVASION]
        mult+=attacker.stages[i] if attacker.stages[i]>0
      end
      basedamage=20*(mult+1)
    when 0x8F # Punishment
      mult=0
      for i in [PBStats::ATTACK,PBStats::DEFENSE,PBStats::SPEED,
                PBStats::SPATK,PBStats::SPDEF,PBStats::ACCURACY,PBStats::EVASION]
        mult+=opponent.stages[i] if opponent.stages[i]>0
      end
      basedamage=[20*(mult+3),200].min
    when 0x90 # Hidden Power
      hp=pbHiddenPower(attacker.iv)
      basedamage=hp[1]
    when 0x91 # Fury Cutter
      basedamage=basedamage<<(attacker.effects[PBEffects::FuryCutter]-1)
    when 0x92 # Echoed Voice
      basedamage*=attacker.pbOwnSide.effects[PBEffects::EchoedVoiceCounter]
    when 0x94 # Present
      basedamage=50
    when 0x95 # Magnitude
      basedamage=71
      basedamage*=2 if PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCA # Dig
    when 0x96 # Natural Gift
      damagearray={
         60 => [:CHERIBERRY,:CHESTOBERRY,:PECHABERRY,:RAWSTBERRY,:ASPEARBERRY,
                :LEPPABERRY,:ORANBERRY,:PERSIMBERRY,:LUMBERRY,:SITRUSBERRY,
                :FIGYBERRY,:WIKIBERRY,:MAGOBERRY,:AGUAVBERRY,:IAPAPABERRY,
                :RAZZBERRY,:OCCABERRY,:PASSHOBERRY,:WACANBERRY,:RINDOBERRY,
                :YACHEBERRY,:CHOPLEBERRY,:KEBIABERRY,:SHUCABERRY,:COBABERRY,
                :PAYAPABERRY,:TANGABERRY,:CHARTIBERRY,:KASIBBERRY,:HABANBERRY,
                :COLBURBERRY,:BABIRIBERRY,:CHILANBERRY],
         70 => [:BLUKBERRY,:NANABBERRY,:WEPEARBERRY,:PINAPBERRY,:POMEGBERRY,
                :KELPSYBERRY,:QUALOTBERRY,:HONDEWBERRY,:GREPABERRY,:TAMATOBERRY,
                :CORNNBERRY,:MAGOSTBERRY,:RABUTABERRY,:NOMELBERRY,:SPELONBERRY,
                :PAMTREBERRY],
         80 => [:WATMELBERRY,:DURINBERRY,:BELUEBERRY,:LIECHIBERRY,:GANLONBERRY,
                :SALACBERRY,:PETAYABERRY,:APICOTBERRY,:LANSATBERRY,:STARFBERRY,
                :ENIGMABERRY,:MICLEBERRY,:CUSTAPBERRY,:JABOCABERRY,:ROWAPBERRY]
      }
      haveanswer=false
      for i in damagearray.keys
        data=damagearray[i]
        if data
          for j in data
            if isConst?(attacker.item,PBItems,j)
              basedamage=i; haveanswer=true; break
            end
          end
        end
        break if haveanswer
      end
    when 0x97 # Trump Card
      dmgs=[200,80,60,50,40]
      ppleft=[move.pp-1,4].min   # PP is reduced before the move is used
      basedamage=dmgs[ppleft]
    when 0x98 # Flail
      n=(48*attacker.hp/attacker.totalhp).floor
      basedamage=20
      basedamage=40 if n<33
      basedamage=80 if n<17
      basedamage=100 if n<10
      basedamage=150 if n<5
      basedamage=200 if n<2
    when 0x99 # Electro Ball
      n=(attacker.pbSpeed/opponent.pbSpeed).floor
      basedamage=40
      basedamage=60 if n>=1
      basedamage=80 if n>=2
      basedamage=120 if n>=3
      basedamage=150 if n>=4
    when 0x9A # Low Kick
      weight=opponent.weight
      basedamage=20
      basedamage=40 if weight>100
      basedamage=60 if weight>250
      basedamage=80 if weight>500
      basedamage=100 if weight>1000
      basedamage=120 if weight>2000
    when 0x9B # Heavy Slam
      n=(attacker.weight/opponent.weight).floor
      basedamage=40
      basedamage=60 if n>=2
      basedamage=80 if n>=3
      basedamage=100 if n>=4
      basedamage=120 if n>=5
    when 0xA0 # Frost Breath
      basedamage*=2
    when 0xBD, 0xBE # Double Kick, Twineedle
      basedamage*=2
    when 0xBF # Triple Kick
      basedamage*=6
    when 0xC0 # Fury Attack
      if attacker.hasWorkingAbility(:SKILLLINK)
        basedamage*=5
      else
        basedamage=(basedamage*19/6).floor
      end
    when 0xC1 # Beat Up
      party=pbParty(attacker.index)
      mult=0
      for i in 0...party.length
        mult+=1 if party[i] && !party[i].egg? &&
                   party[i].hp>0 && party[i].status==0
      end
      basedamage*=mult
    when 0xC4 # SolarBeam
      if pbWeather!=0 && pbWeather!=PBWeather::SUNNYDAY
        basedamage=(basedamage*0.5).floor
      end
    when 0xD0 # Whirlpool
      if skill>=PBTrainerAI.mediumSkill
        basedamage*=2 if PBMoveData.new(opponent.effects[PBEffects::TwoTurnAttack]).function==0xCB # Dive
      end
    when 0xD3 # Rollout
      if skill>=PBTrainerAI.mediumSkill
        basedamage*=2 if attacker.effects[PBEffects::DefenseCurl]
      end
    when 0xE1 # Final Gambit
      basedamage=attacker.hp
    when 0xF7 # Fling
      # TODO
    when 0x113 # Spit Up
      basedamage*=attacker.effects[PBEffects::Stockpile]
    when 0x144
      type=getConst(PBTypes,:FLYING) || -1
      if type>=0
        mult=PBTypes.getCombinedEffectiveness(type,
           opponent.type1,opponent.type2,opponent.effects[PBEffects::Type3])
        basedamage=((basedamage*mult)/8).round
      end
    end
    return basedamage
  end

  def pbRoughDamage(move,attacker,opponent,skill,basedamage)
    # Fixed damage moves
    return basedamage if move.function==0x6A ||   # SonicBoom
                         move.function==0x6B ||   # Dragon Rage
                         move.function==0x6C ||   # Super Fang
                         move.function==0x6D ||   # Night Shade
                         move.function==0x6E ||   # Endeavor
                         move.function==0x6F ||   # Psywave
                         move.function==0x70 ||   # OHKO
                         move.function==0x71 ||   # Counter
                         move.function==0x72 ||   # Mirror Coat
                         move.function==0x73 ||   # Metal Burst
                         move.function==0xE1      # Final Gambit
    type=move.type
    # More accurate move type (includes Normalize, most type-changing moves, etc.)
    if skill>=PBTrainerAI.highSkill
      type=move.pbType(type,attacker,opponent)
    end
    # Technician
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:TECHNICIAN) && basedamage<=60
        basedamage=(basedamage*1.5).round
      end
    end
    # Iron Fist
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hasWorkingAbility(:IRONFIST) && move.isPunchingMove?
        basedamage=(basedamage*1.2).round
      end
    end
    # Reckless
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hasWorkingAbility(:RECKLESS)
        if @function==0xFA ||  # Take Down, etc.
           @function==0xFB ||  # Double-Edge, etc.
           @function==0xFC ||  # Head Smash
           @function==0xFD ||  # Volt Tackle
           @function==0xFE ||  # Flare Blitz
           @function==0x10B || # Jump Kick, Hi Jump Kick
           @function==0x130    # Shadow End
          basedamage=(basedamage*1.2).round
        end
      end
    end
    # Flare Boost
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:FLAREBOOST) &&
         attacker.status==PBStatuses::BURN && move.pbIsSpecial?(type)
        basedamage=(basedamage*1.5).round
      end
    end
    # Toxic Boost
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:TOXICBOOST) &&
         attacker.status==PBStatuses::POISON && move.pbIsPhysical?(type)
        basedamage=(basedamage*1.5).round
      end
    end
    # Analytic
    # Rivalry
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hasWorkingAbility(:RIVALRY) &&
         attacker.gender!=2 && opponent.gender!=2
        if attacker.gender==opponent.gender
          basedamage=(basedamage*1.25).round
        else
          basedamage=(basedamage*0.75).round
        end
      end
    end
    # Sand Force
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hasWorkingAbility(:SANDFORCE) &&
         pbWeather==PBWeather::SANDSTORM &&
         (isConst?(type,PBTypes,:ROCK) ||
         isConst?(type,PBTypes,:GROUND) ||
         isConst?(type,PBTypes,:STEEL))
        basedamage=(basedamage*1.3).round
      end
    end
    # Heatproof
    if skill>=PBTrainerAI.bestSkill
      if opponent.hasWorkingAbility(:HEATPROOF) &&
         isConst?(type,PBTypes,:FIRE)
        basedamage=(basedamage*0.5).round
      end
    end
    # Dry Skin
    if skill>=PBTrainerAI.bestSkill
      if opponent.hasWorkingAbility(:DRYSKIN) &&
         isConst?(type,PBTypes,:FIRE)
        basedamage=(basedamage*1.25).round
      end
    end
    # Sheer Force
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:SHEERFORCE) && move.addlEffect>0
        basedamage=(basedamage*1.3).round
      end
    end
    # Type-boosting items
    if (attacker.hasWorkingItem(:SILKSCARF) && isConst?(type,PBTypes,:NORMAL)) ||
       (attacker.hasWorkingItem(:BLACKBELT) && isConst?(type,PBTypes,:FIGHTING)) ||
       (attacker.hasWorkingItem(:SHARPBEAK) && isConst?(type,PBTypes,:FLYING)) ||
       (attacker.hasWorkingItem(:POISONBARB) && isConst?(type,PBTypes,:POISON)) ||
       (attacker.hasWorkingItem(:SOFTSAND) && isConst?(type,PBTypes,:GROUND)) ||
       (attacker.hasWorkingItem(:HARDSTONE) && isConst?(type,PBTypes,:ROCK)) ||
       (attacker.hasWorkingItem(:SILVERPOWDER) && isConst?(type,PBTypes,:BUG)) ||
       (attacker.hasWorkingItem(:SPELLTAG) && isConst?(type,PBTypes,:GHOST)) ||
       (attacker.hasWorkingItem(:METALCOAT) && isConst?(type,PBTypes,:STEEL)) ||
       (attacker.hasWorkingItem(:CHARCOAL) && isConst?(type,PBTypes,:FIRE)) ||
       (attacker.hasWorkingItem(:MYSTICWATER) && isConst?(type,PBTypes,:WATER)) ||
       (attacker.hasWorkingItem(:MIRACLESEED) && isConst?(type,PBTypes,:GRASS)) ||
       (attacker.hasWorkingItem(:MAGNET) && isConst?(type,PBTypes,:ELECTRIC)) ||
       (attacker.hasWorkingItem(:TWISTEDSPOON) && isConst?(type,PBTypes,:PSYCHIC)) ||
       (attacker.hasWorkingItem(:NEVERMELTICE) && isConst?(type,PBTypes,:ICE)) ||
       (attacker.hasWorkingItem(:DRAGONFANG) && isConst?(type,PBTypes,:DRAGON)) ||
       (attacker.hasWorkingItem(:BLACKGLASSES) && isConst?(type,PBTypes,:DARK))
      basedamage=(basedamage*1.2).round
    end
    if (attacker.hasWorkingItem(:FISTPLATE) && isConst?(type,PBTypes,:FIGHTING)) ||
       (attacker.hasWorkingItem(:SKYPLATE) && isConst?(type,PBTypes,:FLYING)) ||
       (attacker.hasWorkingItem(:TOXICPLATE) && isConst?(type,PBTypes,:POISON)) ||
       (attacker.hasWorkingItem(:EARTHPLATE) && isConst?(type,PBTypes,:GROUND)) ||
       (attacker.hasWorkingItem(:STONEPLATE) && isConst?(type,PBTypes,:ROCK)) ||
       (attacker.hasWorkingItem(:INSECTPLATE) && isConst?(type,PBTypes,:BUG)) ||
       (attacker.hasWorkingItem(:SPOOKYPLATE) && isConst?(type,PBTypes,:GHOST)) ||
       (attacker.hasWorkingItem(:IRONPLATE) && isConst?(type,PBTypes,:STEEL)) ||
       (attacker.hasWorkingItem(:FLAMEPLATE) && isConst?(type,PBTypes,:FIRE)) ||
       (attacker.hasWorkingItem(:SPLASHPLATE) && isConst?(type,PBTypes,:WATER)) ||
       (attacker.hasWorkingItem(:MEADOWPLATE) && isConst?(type,PBTypes,:GRASS)) ||
       (attacker.hasWorkingItem(:ZAPPLATE) && isConst?(type,PBTypes,:ELECTRIC)) ||
       (attacker.hasWorkingItem(:MINDPLATE) && isConst?(type,PBTypes,:PSYCHIC)) ||
       (attacker.hasWorkingItem(:ICICLEPLATE) && isConst?(type,PBTypes,:ICE)) ||
       (attacker.hasWorkingItem(:DRACOPLATE) && isConst?(type,PBTypes,:DRAGON)) ||
       (attacker.hasWorkingItem(:DREADPLATE) && isConst?(type,PBTypes,:DARK)) ||
       (attacker.hasWorkingItem(:PIXIEPLATE) && isConst?(type,PBTypes,:FAIRY))
      basedamage=(basedamage*1.2).round
    end
    if (attacker.hasWorkingItem(:NORMALGEM) && isConst?(type,PBTypes,:NORMAL)) ||
       (attacker.hasWorkingItem(:FIGHTINGGEM) && isConst?(type,PBTypes,:FIGHTING)) ||
       (attacker.hasWorkingItem(:FLYINGGEM) && isConst?(type,PBTypes,:FLYING)) ||
       (attacker.hasWorkingItem(:POISONGEM) && isConst?(type,PBTypes,:POISON)) ||
       (attacker.hasWorkingItem(:GROUNDGEM) && isConst?(type,PBTypes,:GROUND)) ||
       (attacker.hasWorkingItem(:ROCKGEM) && isConst?(type,PBTypes,:ROCK)) ||
       (attacker.hasWorkingItem(:BUGGEM) && isConst?(type,PBTypes,:BUG)) ||
       (attacker.hasWorkingItem(:GHOSTGEM) && isConst?(type,PBTypes,:GHOST)) ||
       (attacker.hasWorkingItem(:STEELGEM) && isConst?(type,PBTypes,:STEEL)) ||
       (attacker.hasWorkingItem(:FIREGEM) && isConst?(type,PBTypes,:FIRE)) ||
       (attacker.hasWorkingItem(:WATERGEM) && isConst?(type,PBTypes,:WATER)) ||
       (attacker.hasWorkingItem(:GRASSGEM) && isConst?(type,PBTypes,:GRASS)) ||
       (attacker.hasWorkingItem(:ELECTRICGEM) && isConst?(type,PBTypes,:ELECTRIC)) ||
       (attacker.hasWorkingItem(:PSYCHICGEM) && isConst?(type,PBTypes,:PSYCHIC)) ||
       (attacker.hasWorkingItem(:ICEGEM) && isConst?(type,PBTypes,:ICE)) ||
       (attacker.hasWorkingItem(:DRAGONGEM) && isConst?(type,PBTypes,:DRAGON)) ||
       (attacker.hasWorkingItem(:DARKGEM) && isConst?(type,PBTypes,:DARK)) ||
       (attacker.hasWorkingItem(:FAIRYGEM) && isConst?(type,PBTypes,:FAIRY))
      basedamage=(basedamage*1.5).round
    end
    if attacker.hasWorkingItem(:ROCKINCENSE) && isConst?(type,PBTypes,:ROCK)
      basedamage=(basedamage*1.2).round
    end
    if attacker.hasWorkingItem(:ROSEINCENSE) && isConst?(type,PBTypes,:GRASS)
      basedamage=(basedamage*1.2).round
    end
    if attacker.hasWorkingItem(:SEAINCENSE) && isConst?(type,PBTypes,:WATER)
      basedamage=(basedamage*1.2).round
    end
    if attacker.hasWorkingItem(:WAVEINCENSE) && isConst?(type,PBTypes,:WATER)
      basedamage=(basedamage*1.2).round
    end
    if attacker.hasWorkingItem(:ODDINCENSE) && isConst?(type,PBTypes,:PSYCHIC)
      basedamage=(basedamage*1.2).round
    end
    # Muscle Band
    if attacker.hasWorkingItem(:MUSCLEBAND) && move.pbIsPhysical?(type)
      basedamage=(basedamage*1.1).round
    end
    # Wise Glasses
    if attacker.hasWorkingItem(:WISEGLASSES) && move.pbIsSpecial?(type)
      basedamage=(basedamage*1.1).round
    end
    # Legendary Orbs
    if isConst?(attacker.species,PBSpecies,:PALKIA) &&
       attacker.hasWorkingItem(:LUSTROUSORB) &&
       (isConst?(type,PBTypes,:DRAGON) || isConst?(type,PBTypes,:WATER))
      basedamage=(basedamage*1.2).round
    end
    if isConst?(attacker.species,PBSpecies,:DIALGA) &&
       attacker.hasWorkingItem(:ADAMANTORB) &&
       (isConst?(type,PBTypes,:DRAGON) || isConst?(type,PBTypes,:STEEL))
      basedamage=(basedamage*1.2).round
    end
    if isConst?(attacker.species,PBSpecies,:GIRATINA) &&
       attacker.hasWorkingItem(:GRISEOUSORB) &&
       (isConst?(type,PBTypes,:DRAGON) || isConst?(type,PBTypes,:GHOST))
      basedamage=(basedamage*1.2).round
    end
    # pbBaseDamageMultiplier - TODO
    # Me First
    # Charge
    if attacker.effects[PBEffects::Charge]>0 && isConst?(type,PBTypes,:ELECTRIC)
      basedamage=(basedamage*2.0).round
    end
    # Helping Hand - n/a
    # Water Sport
    if skill>=PBTrainerAI.mediumSkill
      if isConst?(type,PBTypes,:FIRE)
        for i in 0...4
          if @battlers[i].effects[PBEffects::WaterSport] && !@battlers[i].fainted?
            basedamage=(basedamage*0.33).round
            break
          end
        end
      end
    end
    # Mud Sport
    if skill>=PBTrainerAI.mediumSkill
      if isConst?(type,PBTypes,:ELECTRIC)
        for i in 0...4
          if @battlers[i].effects[PBEffects::MudSport] && !@battlers[i].fainted?
            basedamage=(basedamage*0.33).round
            break
          end
        end
      end
    end
    # Get base attack stat
    atk=pbRoughStat(attacker,PBStats::ATTACK,skill)
    if move.function==0x121 # Foul Play
      atk=pbRoughStat(opponent,PBStats::ATTACK,skill)
    end
    if type>=0 && move.pbIsSpecial?(type)
      atk=pbRoughStat(attacker,PBStats::SPATK,skill)
      if move.function==0x121 # Foul Play
        atk=pbRoughStat(opponent,PBStats::SPATK,skill)
      end
    end
    # Hustle
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:HUSTLE) && move.pbIsPhysical?(type)
        atk=(atk*1.5).round
      end
    end
    # Thick Fat
    if skill>=PBTrainerAI.bestSkill
      if opponent.hasWorkingAbility(:THICKFAT) &&
         (isConst?(type,PBTypes,:ICE) || isConst?(type,PBTypes,:FIRE))
        atk=(atk*0.5).round
      end
    end
    # Pinch abilities
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hp<=(attacker.totalhp/3).floor
        if (attacker.hasWorkingAbility(:OVERGROW) && isConst?(type,PBTypes,:GRASS)) ||
           (attacker.hasWorkingAbility(:BLAZE) && isConst?(type,PBTypes,:FIRE)) ||
           (attacker.hasWorkingAbility(:TORRENT) && isConst?(type,PBTypes,:WATER)) ||
           (attacker.hasWorkingAbility(:SWARM) && isConst?(type,PBTypes,:BUG))
          atk=(atk*1.5).round
        end
      end
    end
    # Guts
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:GUTS) &&
         attacker.status!=0 && move.pbIsPhysical?(type)
        atk=(atk*1.5).round
      end
    end
    # Plus, Minus
    if skill>=PBTrainerAI.mediumSkill
      if (attacker.hasWorkingAbility(:PLUS) ||
         attacker.hasWorkingAbility(:MINUS)) && move.pbIsSpecial?(type)
        partner=attacker.pbPartner
        if partner.hasWorkingAbility(:PLUS) || partner.hasWorkingAbility(:MINUS)
          atk=(atk*1.5).round
        end
      end
    end
    # Defeatist
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hasWorkingAbility(:DEFEATIST) &&
         attacker.hp<=(attacker.totalhp/2).floor
        atk=(atk*0.5).round
      end
    end
    # Pure Power, Huge Power
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hasWorkingAbility(:PUREPOWER) ||
         attacker.hasWorkingAbility(:HUGEPOWER)
        atk=(atk*2.0).round
      end
    end
    # Solar Power
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:SOLARPOWER) &&
         pbWeather==PBWeather::SUNNYDAY && move.pbIsSpecial?(type)
        atk=(atk*1.5).round
      end
    end
    # Flash Fire
    if skill>=PBTrainerAI.highSkill
      if attacker.hasWorkingAbility(:FLASHFIRE) &&
         attacker.effects[PBEffects::FlashFire] && isConst?(type,PBTypes,:FIRE)
        atk=(atk*1.5).round
      end
    end
    # Slow Start
    if skill>=PBTrainerAI.mediumSkill
      if attacker.hasWorkingAbility(:SLOWSTART) &&
         attacker.turncount<5 && move.pbIsPhysical?(type)
        atk=(atk*0.5).round
      end
    end
    # Flower Gift
    if skill>=PBTrainerAI.highSkill
      if pbWeather==PBWeather::SUNNYDAY && move.pbIsPhysical?(type)
        if attacker.hasWorkingAbility(:FLOWERGIFT) &&
           isConst?(attacker.species,PBSpecies,:CHERRIM)
          atk=(atk*1.5).round
        end
        if attacker.pbPartner.hasWorkingAbility(:FLOWERGIFT) &&
           isConst?(attacker.pbPartner.species,PBSpecies,:CHERRIM)
          atk=(atk*1.5).round
        end
      end
    end
    # Attack-boosting items
    if attacker.hasWorkingItem(:THICKCLUB) &&
       (isConst?(attacker.species,PBSpecies,:CUBONE) ||
       isConst?(attacker.species,PBSpecies,:MAROWAK)) && move.pbIsPhysical?(type)
      atk=(atk*2.0).round
    end
    if attacker.hasWorkingItem(:DEEPSEATOOTH) &&
       isConst?(attacker.species,PBSpecies,:CLAMPERL) && move.pbIsSpecial?(type)
      atk=(atk*2.0).round
    end
    if attacker.hasWorkingItem(:LIGHTBALL) &&
       isConst?(attacker.species,PBSpecies,:PIKACHU)
      atk=(atk*2.0).round
    end
    if attacker.hasWorkingItem(:SOULDEW) &&
       (isConst?(attacker.species,PBSpecies,:LATIAS) ||
       isConst?(attacker.species,PBSpecies,:LATIOS)) && move.pbIsSpecial?(type)
      atk=(atk*1.5).round
    end
    if attacker.hasWorkingItem(:CHOICEBAND) && move.pbIsPhysical?(type)
      atk=(atk*1.5).round
    end
    if attacker.hasWorkingItem(:CHOICESPECS) && move.pbIsSpecial?(type)
      atk=(atk*1.5).round
    end
    # Get base defense stat
    defense=pbRoughStat(opponent,PBStats::DEFENSE,skill)
    applysandstorm=false
    if type>=0 && move.pbIsSpecial?(type)
      if move.function!=0x122 # Psyshock
        defense=pbRoughStat(opponent,PBStats::SPDEF,skill)
        applysandstorm=true
      end
    end
    # Sandstorm weather
    if skill>=PBTrainerAI.highSkill
      if pbWeather==PBWeather::SANDSTORM &&
         opponent.pbHasType?(:ROCK) && applysandstorm
        defense=(defense*1.5).round
      end
    end
    # Marvel Scale
    if skill>=PBTrainerAI.bestSkill
      if opponent.hasWorkingAbility(:MARVELSCALE) &&
         opponent.status>0 && move.pbIsPhysical?(type)
        defense=(defense*1.5).round
      end
    end
    # Flower Gift
    if skill>=PBTrainerAI.bestSkill
      if pbWeather==PBWeather::SUNNYDAY && move.pbIsSpecial?(type)
        if opponent.hasWorkingAbility(:FLOWERGIFT) &&
           isConst?(opponent.species,PBSpecies,:CHERRIM)
          defense=(defense*1.5).round
        end
        if opponent.pbPartner.hasWorkingAbility(:FLOWERGIFT) &&
           isConst?(opponent.pbPartner.species,PBSpecies,:CHERRIM)
          defense=(defense*1.5).round
        end
      end
    end
    # Defense-boosting items
    if skill>=PBTrainerAI.highSkill
      if opponent.hasWorkingItem(:EVIOLITE)
        evos=pbGetEvolvedFormData(opponent.pokemon.fSpecies)
        if evos && evos.length>0
          defense=(defense*1.5).round
        end
      end
      if opponent.hasWorkingItem(:DEEPSEASCALE) &&
         isConst?(opponent.species,PBSpecies,:CLAMPERL) && move.pbIsSpecial?(type)
        defense=(defense*2.0).round
      end
      if opponent.hasWorkingItem(:METALPOWDER) &&
         isConst?(opponent.species,PBSpecies,:DITTO) &&
         !opponent.effects[PBEffects::Transform] && move.pbIsPhysical?(type)
        defense=(defense*2.0).round
      end
      if opponent.hasWorkingItem(:SOULDEW) &&
         (isConst?(opponent.species,PBSpecies,:LATIAS) ||
         isConst?(opponent.species,PBSpecies,:LATIOS)) && move.pbIsSpecial?(type)
        defense=(defense*1.5).round
      end
    end
    defense = [defense.round,1].max
    # Main damage calculation
    damage=(((2.0*attacker.level/5+2).floor*basedamage*atk/defense).floor/50).floor+2
    # Multi-targeting attacks
    if skill>=PBTrainerAI.highSkill
      if move.pbTargetsMultiple?(attacker)
        damage=(damage*0.75).round
      end
    end
    # Weather
    if skill>=PBTrainerAI.mediumSkill
      case pbWeather
      when PBWeather::SUNNYDAY
        if isConst?(type,PBTypes,:FIRE)
          damage=(damage*1.5).round
        elsif isConst?(type,PBTypes,:WATER)
          damage=(damage*0.5).round
        end
      when PBWeather::RAINDANCE
        if isConst?(type,PBTypes,:FIRE)
          damage=(damage*0.5).round
        elsif isConst?(type,PBTypes,:WATER)
          damage=(damage*1.5).round
        end
      end
    end
    # Critical hits - n/a
    # Random variance - n/a
    # STAB
    if skill>=PBTrainerAI.mediumSkill
      if attacker.pbHasType?(type)
        if attacker.hasWorkingAbility(:ADAPTABILITY) &&
           skill>=PBTrainerAI.highSkill
          damage=(damage*2).round
        else
          damage=(damage*1.5).round
        end
      end
    end
    # Type effectiveness
    typemod=pbTypeModifier(type,attacker,opponent)
    if skill>=PBTrainerAI.highSkill
      damage=(damage*typemod*1.0/8).round
    end
    # Burn
    if skill>=PBTrainerAI.mediumSkill
      if attacker.status==PBStatuses::BURN && move.pbIsPhysical?(type) &&
         !attacker.hasWorkingAbility(:GUTS)
        damage=(damage*0.5).round
      end
    end
    # Make sure damage is at least 1
    damage=1 if damage<1
    # Reflect
    if skill>=PBTrainerAI.highSkill
      if opponent.pbOwnSide.effects[PBEffects::Reflect]>0 && move.pbIsPhysical?(type)
        if !opponent.pbPartner.fainted?
          damage=(damage*0.66).round
        else
          damage=(damage*0.5).round
        end
      end
    end
    # Light Screen
    if skill>=PBTrainerAI.highSkill
      if opponent.pbOwnSide.effects[PBEffects::LightScreen]>0 && move.pbIsSpecial?(type)
        if !opponent.pbPartner.fainted?
          damage=(damage*0.66).round
        else
          damage=(damage*0.5).round
        end
      end
    end
    # Multiscale
    if skill>=PBTrainerAI.bestSkill
      if opponent.hasWorkingAbility(:MULTISCALE) &&
         opponent.hp==opponent.totalhp
        damage=(damage*0.5).round
      end
    end
    # Tinted Lens
    if skill>=PBTrainerAI.bestSkill
      if attacker.hasWorkingAbility(:TINTEDLENS) && typemod<8
        damage=(damage*2.0).round
      end
    end
    # Friend Guard
    if skill>=PBTrainerAI.bestSkill
      if opponent.pbPartner.hasWorkingAbility(:FRIENDGUARD)
        damage=(damage*0.75).round
      end
    end
    # Sniper - n/a
    # Solid Rock, Filter
    if skill>=PBTrainerAI.bestSkill
      if (opponent.hasWorkingAbility(:SOLIDROCK) || opponent.hasWorkingAbility(:FILTER)) &&
         typemod>8
        damage=(damage*0.75).round
      end
    end
    # Final damage-altering items
    if attacker.hasWorkingItem(:METRONOME)
      if attacker.effects[PBEffects::Metronome]>4
        damage=(damage*2.0).round
      else
        met=1.0+attacker.effects[PBEffects::Metronome]*0.2
        damage=(damage*met).round
      end
    end
    if attacker.hasWorkingItem(:EXPERTBELT) && typemod>8
      damage=(damage*1.2).round
    end
    if attacker.hasWorkingItem(:LIFEORB)
      damage=(damage*1.3).round
    end
    if typemod>8 && skill>=PBTrainerAI.highSkill
      if (opponent.hasWorkingItem(:CHOPLEBERRY) && isConst?(type,PBTypes,:FIGHTING)) ||
         (opponent.hasWorkingItem(:COBABERRY) && isConst?(type,PBTypes,:FLYING)) ||
         (opponent.hasWorkingItem(:KEBIABERRY) && isConst?(type,PBTypes,:POISON)) ||
         (opponent.hasWorkingItem(:SHUCABERRY) && isConst?(type,PBTypes,:GROUND)) ||
         (opponent.hasWorkingItem(:CHARTIBERRY) && isConst?(type,PBTypes,:ROCK)) ||
         (opponent.hasWorkingItem(:TANGABERRY) && isConst?(type,PBTypes,:BUG)) ||
         (opponent.hasWorkingItem(:KASIBBERRY) && isConst?(type,PBTypes,:GHOST)) ||
         (opponent.hasWorkingItem(:BABIRIBERRY) && isConst?(type,PBTypes,:STEEL)) ||
         (opponent.hasWorkingItem(:OCCABERRY) && isConst?(type,PBTypes,:FIRE)) ||
         (opponent.hasWorkingItem(:PASSHOBERRY) && isConst?(type,PBTypes,:WATER)) ||
         (opponent.hasWorkingItem(:RINDOBERRY) && isConst?(type,PBTypes,:GRASS)) ||
         (opponent.hasWorkingItem(:WACANBERRY) && isConst?(type,PBTypes,:ELECTRIC)) ||
         (opponent.hasWorkingItem(:PAYAPABERRY) && isConst?(type,PBTypes,:PSYCHIC)) ||
         (opponent.hasWorkingItem(:YACHEBERRY) && isConst?(type,PBTypes,:ICE)) ||
         (opponent.hasWorkingItem(:HABANBERRY) && isConst?(type,PBTypes,:DRAGON)) ||
         (opponent.hasWorkingItem(:COLBURBERRY) && isConst?(type,PBTypes,:DARK))
        damage=(damage*0.5).round
      end
    end
    if skill>=PBTrainerAI.highSkill
      if opponent.hasWorkingItem(:CHILANBERRY) && isConst?(type,PBTypes,:NORMAL)
        damage=(damage*0.5).round
      end
    end
    # pbModifyDamage - TODO
    # "AI-specific calculations below"
    # Increased critical hit rates
    if skill>=PBTrainerAI.mediumSkill
      c=0
      c+=attacker.effects[PBEffects::FocusEnergy]
      c+=1 if move.hasHighCriticalRate?
      c+=1 if (attacker.inHyperMode? rescue false) && isConst?(self.type,PBTypes,:SHADOW)
      c+=2 if isConst?(attacker.species,PBSpecies,:CHANSEY) && 
              attacker.hasWorkingItem(:LUCKYPUNCH)
      c+=2 if isConst?(attacker.species,PBSpecies,:FARFETCHD) && 
              attacker.hasWorkingItem(:STICK)
      c+=1 if attacker.hasWorkingAbility(:SUPERLUCK)
      c+=1 if attacker.hasWorkingItem(:SCOPELENS)
      c+=1 if attacker.hasWorkingItem(:RAZORCLAW)
      c=4 if c>4
      basedamage+=(basedamage*0.1*c)
    end
    return damage
  end

  def pbRoughAccuracy(move,attacker,opponent,skill)
    # Get base accuracy
    baseaccuracy=move.accuracy
    if skill>=PBTrainerAI.mediumSkill
      if pbWeather==PBWeather::SUNNYDAY &&
         (move.function==0x08 || move.function==0x15) # Thunder, Hurricane
        accuracy=50
      end
    end
    # Accuracy stages
    accstage=attacker.stages[PBStats::ACCURACY]
    accstage=0 if opponent.hasWorkingAbility(:UNAWARE)
    accuracy=(accstage>=0) ? (accstage+3)*100.0/3 : 300.0/(3-accstage)
    evastage=opponent.stages[PBStats::EVASION]
    evastage-=2 if @field.effects[PBEffects::Gravity]>0
    evastage=-6 if evastage<-6
    evastage=0 if opponent.effects[PBEffects::Foresight] ||
                  opponent.effects[PBEffects::MiracleEye] ||
                  move.function==0xA9 || # Chip Away
                  attacker.hasWorkingAbility(:UNAWARE)
    evasion=(evastage>=0) ? (evastage+3)*100.0/3 : 300.0/(3-evastage)
    accuracy*=baseaccuracy/evasion
    # Accuracy modifiers
    if skill>=PBTrainerAI.mediumSkill
      accuracy*=1.3 if attacker.hasWorkingAbility(:COMPOUNDEYES)
      accuracy*=1.1 if attacker.hasWorkingAbility(:VICTORYSTAR)
      if skill>=PBTrainerAI.highSkill
        partner=attacker.pbPartner
        accuracy*=1.1 if partner && partner.hasWorkingAbility(:VICTORYSTAR)
      end
      accuracy*=1.2 if attacker.effects[PBEffects::MicleBerry]
      accuracy*=1.1 if attacker.hasWorkingItem(:WIDELENS)
      if skill>=PBTrainerAI.highSkill
        accuracy*=0.8 if attacker.hasWorkingAbility(:HUSTLE) &&
                         move.basedamage>0 &&
                         move.pbIsPhysical?(move.pbType(move.type,attacker,opponent))
      end
      if skill>=PBTrainerAI.bestSkill
        accuracy/=2 if opponent.hasWorkingAbility(:WONDERSKIN) &&
                       move.basedamage==0 &&
                       attacker.pbIsOpposing?(opponent.index)
        accuracy/=1.2 if opponent.hasWorkingAbility(:TANGLEDFEET) &&
                         opponent.effects[PBEffects::Confusion]>0
        accuracy/=1.2 if pbWeather==PBWeather::SANDSTORM &&
                         opponent.hasWorkingAbility(:SANDVEIL)
        accuracy/=1.2 if pbWeather==PBWeather::HAIL &&
                         opponent.hasWorkingAbility(:SNOWCLOAK)
      end
      if skill>=PBTrainerAI.highSkill
        accuracy/=1.1 if opponent.hasWorkingItem(:BRIGHTPOWDER)
        accuracy/=1.1 if opponent.hasWorkingItem(:LAXINCENSE)
      end
    end
    accuracy=100 if accuracy>100
    # Override accuracy
    accuracy=125 if move.accuracy==0   # Doesn't do accuracy check (always hits)
    accuracy=125 if move.function==0xA5 # Swift
    if skill>=PBTrainerAI.mediumSkill
      accuracy=125 if opponent.effects[PBEffects::LockOn]>0 &&
                      opponent.effects[PBEffects::LockOnPos]==attacker.index
      if skill>=PBTrainerAI.highSkill
        accuracy=125 if attacker.hasWorkingAbility(:NOGUARD) ||
                        opponent.hasWorkingAbility(:NOGUARD)
      end
      accuracy=125 if opponent.effects[PBEffects::Telekinesis]>0
      case pbWeather
      when PBWeather::HAIL
        accuracy=125 if move.function==0x0D # Blizzard
      when PBWeather::RAINDANCE
        accuracy=125 if move.function==0x08 || move.function==0x15 # Thunder, Hurricane
      end
      if move.function==0x70 # OHKO moves
        accuracy=move.accuracy+attacker.level-opponent.level
        accuracy=0 if opponent.hasWorkingAbility(:STURDY)
        accuracy=0 if opponent.level>attacker.level
      end
    end
    return accuracy
  end

################################################################################
# Choose a move to use.
################################################################################
  def pbChooseMoves(index)
    attacker=@battlers[index]
    scores=[0,0,0,0]
    targets=nil
    myChoices=[]
    totalscore=0
    target=-1
    skill=0
    wildbattle=!@opponent && pbIsOpposing?(index)
    if wildbattle # If wild battle
      for i in 0...4
        if pbCanChooseMove?(index,i,false)
          scores[i]=100
          myChoices.push(i)
          totalscore+=100
        end
      end
    else
      skill=pbGetOwner(attacker.index).skill || 0
      opponent=attacker.pbOppositeOpposing
      if @doublebattle && !opponent.fainted? && !opponent.pbPartner.fainted?
        # Choose a target and move.  Also care about partner.
        otheropp=opponent.pbPartner
        scoresAndTargets=[]
        targets=[-1,-1,-1,-1]
        for i in 0...4
          if pbCanChooseMove?(index,i,false)
            score1=pbGetMoveScore(attacker.moves[i],attacker,opponent,skill)
            score2=pbGetMoveScore(attacker.moves[i],attacker,otheropp,skill)
            if (attacker.moves[i].target&0x20)!=0 # Target's user's side
              if attacker.pbPartner.fainted? # No partner
                score1*=5/3
                score2*=5/3
              else
                # If this move can also target the partner, get the partner's
                # score too
                s=pbGetMoveScore(attacker.moves[i],attacker,attacker.pbPartner,skill)
                if s>=140 # Highly effective
                  score1*=1/3
                  score2*=1/3
                elsif s>=100 # Very effective
                  score1*=2/3
                  score2*=2/3
                elsif s>=40 # Less effective
                  score1*=4/3
                  score2*=4/3
                else # Hardly effective
                  score1*=5/3
                  score2*=5/3
                end
              end
            end
            myChoices.push(i)
            scoresAndTargets.push([i*2,i,score1,opponent.index])
            scoresAndTargets.push([i*2+1,i,score2,otheropp.index])
          end
        end
        scoresAndTargets.sort!{|a,b|
           if a[2]==b[2] # if scores are equal
             a[0]<=>b[0] # sort by index (for stable comparison)
           else
             b[2]<=>a[2]
           end
        }
        for i in 0...scoresAndTargets.length
          idx=scoresAndTargets[i][1]
          thisScore=scoresAndTargets[i][2]
          if thisScore>0
            if scores[idx]==0 || ((scores[idx]==thisScore && pbAIRandom(10)<5) ||
               (scores[idx]!=thisScore && pbAIRandom(10)<3))
              scores[idx]=thisScore
              targets[idx]=scoresAndTargets[i][3]
            end
          end
        end
        for i in 0...4
          scores[i]=0 if scores[i]<0
          totalscore+=scores[i]
        end
      else
        # Choose a move. There is only 1 opposing Pokémon.
        if @doublebattle && opponent.fainted?
          opponent=opponent.pbPartner
        end
        for i in 0...4
          if pbCanChooseMove?(index,i,false)
            scores[i]=pbGetMoveScore(attacker.moves[i],attacker,opponent,skill)
            myChoices.push(i)
          end
          scores[i]=0 if scores[i]<0
          totalscore+=scores[i]
        end
      end
    end
    maxscore=0
    for i in 0...4
      maxscore=scores[i] if scores[i] && scores[i]>maxscore
    end
    # Minmax choices depending on AI
    if !wildbattle && skill>=PBTrainerAI.mediumSkill
      threshold=(skill>=PBTrainerAI.bestSkill) ? 1.5 : (skill>=PBTrainerAI.highSkill) ? 2 : 3
      newscore=(skill>=PBTrainerAI.bestSkill) ? 5 : (skill>=PBTrainerAI.highSkill) ? 10 : 15
      for i in 0...scores.length
        if scores[i]>newscore && scores[i]*threshold<maxscore
          totalscore-=(scores[i]-newscore)
          scores[i]=newscore
        end
      end
      maxscore=0
      for i in 0...4
        maxscore=scores[i] if scores[i] && scores[i]>maxscore
      end
    end
    if $INTERNAL
      x="[AI] #{attacker.pbThis}'s moves: "
      j=0
      for i in 0...4
        if attacker.moves[i].id!=0
          x+=", " if j>0
          x+=PBMoves.getName(attacker.moves[i].id)+"="+scores[i].to_s
          j+=1
        end
      end
      PBDebug.log(x)
    end
    if !wildbattle && maxscore>100
      stdev=pbStdDev(scores)
      if stdev>=40 && pbAIRandom(10)!=0
        # If standard deviation is 40 or more,
        # there is a highly preferred move. Choose it.
        preferredMoves=[]
        for i in 0...4
          if attacker.moves[i].id!=0 && (scores[i]>=maxscore*0.8 || scores[i]>=200)
            preferredMoves.push(i)
            preferredMoves.push(i) if scores[i]==maxscore # Doubly prefer the best move
          end
        end
        if preferredMoves.length>0
          i=preferredMoves[pbAIRandom(preferredMoves.length)]
          PBDebug.log("[AI] Prefer #{PBMoves.getName(attacker.moves[i].id)}")
          pbRegisterMove(index,i,false)
          target=targets[i] if targets
          if @doublebattle && target>=0
            pbRegisterTarget(index,target)
          end
          return
        end
      end
    end
    if !wildbattle && attacker.turncount
      badmoves=false
      if ((maxscore<=20 && attacker.turncount>2) ||
         (maxscore<=30 && attacker.turncount>5)) && pbAIRandom(10)<8
        badmoves=true
      end
      if totalscore<100 && attacker.turncount>1
        badmoves=true
        movecount=0
        for i in 0...4
          if attacker.moves[i].id!=0
            if scores[i]>0 && attacker.moves[i].basedamage>0
              badmoves=false
            end
            movecount+=1
          end
        end
        badmoves=badmoves && pbAIRandom(10)!=0
      end
      if badmoves
        # Attacker has terrible moves, try switching instead
        if pbEnemyShouldWithdrawEx?(index,true)
          if $INTERNAL
            PBDebug.log("[AI] Switching due to terrible moves")
            PBDebug.log([index,@choices[index][0],@choices[index][1],
               pbCanChooseNonActive?(index),
               @battlers[index].pbNonActivePokemonCount()].inspect)
          end
          return
        end
      end
    end
    if maxscore<=0
      # If all scores are 0 or less, choose a move at random
      if myChoices.length>0
        pbRegisterMove(index,myChoices[pbAIRandom(myChoices.length)],false)
      else
        pbAutoChooseMove(index)
      end
    else
      randnum=pbAIRandom(totalscore)
      cumtotal=0
      for i in 0...4
        if scores[i]>0
          cumtotal+=scores[i]
          if randnum<cumtotal
            pbRegisterMove(index,i,false)
            target=targets[i] if targets
            break
          end
        end
      end
    end
    PBDebug.log("[AI] Will use #{@choices[index][2].name}") if @choices[index][2]
    if @doublebattle && target>=0
      pbRegisterTarget(index,target)
    end
  end

################################################################################
# Decide whether the opponent should Mega Evolve their Pokémon.
################################################################################
  def pbEnemyShouldMegaEvolve?(index)
    # Simple "always should if possible"
    return pbCanMegaEvolve?(index)
  end

################################################################################
# Decide whether the opponent should use an item on the Pokémon.
################################################################################
  def pbEnemyShouldUseItem?(index)
    item=pbEnemyItemToUse(index)
    if item>0
      pbRegisterItem(index,item,nil)
      return true
    end
    return false
  end

  def pbEnemyItemAlreadyUsed?(index,item,items)
    if @choices[1][0]==3 && @choices[1][1]==item
      qty=0
      for i in items
        qty+=1 if i==item
      end
      return true if qty<=1
    end
    return false
  end

  def pbEnemyItemToUse(index)
    return 0 if !@internalbattle
    items=pbGetOwnerItems(index)
    return 0 if !items
    battler=@battlers[index]
    return 0 if battler.fainted? ||
                battler.effects[PBEffects::Embargo]>0
    hashpitem=false
    for i in items
      next if pbEnemyItemAlreadyUsed?(index,i,items)
      if isConst?(i,PBItems,:POTION) || 
         isConst?(i,PBItems,:SUPERPOTION) || 
         isConst?(i,PBItems,:HYPERPOTION) || 
         isConst?(i,PBItems,:MAXPOTION) ||
         isConst?(i,PBItems,:FULLRESTORE)
        hashpitem=true
      end
    end
    for i in items
      next if pbEnemyItemAlreadyUsed?(index,i,items)
      if isConst?(i,PBItems,:FULLRESTORE)
        return i if battler.hp<=battler.totalhp/4
        return i if battler.hp<=battler.totalhp/2 && pbAIRandom(10)<3
        return i if battler.hp<=battler.totalhp*2/3 &&
                    (battler.status>0 || battler.effects[PBEffects::Confusion]>0) &&
                    pbAIRandom(10)<3
      elsif isConst?(i,PBItems,:POTION) || 
         isConst?(i,PBItems,:SUPERPOTION) || 
         isConst?(i,PBItems,:HYPERPOTION) || 
         isConst?(i,PBItems,:MAXPOTION)
        return i if battler.hp<=battler.totalhp/4
        return i if battler.hp<=battler.totalhp/2 && pbAIRandom(10)<3
      elsif isConst?(i,PBItems,:FULLHEAL)
        return i if !hashpitem &&
                    (battler.status>0 || battler.effects[PBEffects::Confusion]>0)
      elsif isConst?(i,PBItems,:XATTACK) ||
            isConst?(i,PBItems,:XDEFEND) ||
            isConst?(i,PBItems,:XDEFENSE) ||
            isConst?(i,PBItems,:XSPEED) ||
            isConst?(i,PBItems,:XSPECIAL) ||
            isConst?(i,PBItems,:XSPATK) ||
            isConst?(i,PBItems,:XSPDEF) ||
            isConst?(i,PBItems,:XACCURACY)
        stat=0
        stat=PBStats::ATTACK if isConst?(i,PBItems,:XATTACK)
        stat=PBStats::DEFENSE if isConst?(i,PBItems,:XDEFEND)
        stat=PBStats::DEFENSE if isConst?(i,PBItems,:XDEFENSE)
        stat=PBStats::SPEED if isConst?(i,PBItems,:XSPEED)
        stat=PBStats::SPATK if isConst?(i,PBItems,:XSPECIAL)
        stat=PBStats::SPATK if isConst?(i,PBItems,:XSPATK)
        stat=PBStats::SPDEF if isConst?(i,PBItems,:XSPDEF)
        stat=PBStats::ACCURACY if isConst?(i,PBItems,:XACCURACY)
        if stat>0 && !battler.pbTooHigh?(stat)
          return i if pbAIRandom(10)<3-battler.stages[stat]
        end
      end
    end
    return 0
  end

################################################################################
# Decide whether the opponent should switch Pokémon.
################################################################################
  def pbEnemyShouldWithdraw?(index)
#    if $INTERNAL && !pbIsOpposing?(index)
#      return pbEnemyShouldWithdrawOld?(index)
#    end
    return pbEnemyShouldWithdrawEx?(index,false)
  end

  def pbEnemyShouldWithdrawEx?(index,alwaysSwitch)
    return false if !@opponent
    shouldswitch=alwaysSwitch
    typecheck=false
    batonpass=-1
    movetype=-1
    skill=pbGetOwner(index).skill || 0
    if @opponent && !shouldswitch && @battlers[index].turncount>0
      if skill>=PBTrainerAI.highSkill
        opponent=@battlers[index].pbOppositeOpposing
        opponent=opponent.pbPartner if opponent.fainted?
        if !opponent.fainted? && opponent.lastMoveUsed>0 && 
           (opponent.level-@battlers[index].level).abs<=6
          move=PBMoveData.new(opponent.lastMoveUsed)
          typemod=pbTypeModifier(move.type,@battlers[index],@battlers[index])
          movetype=move.type
          if move.basedamage>70 && typemod>8
            shouldswitch=(pbAIRandom(100)<30)
          elsif move.basedamage>50 && typemod>8
            shouldswitch=(pbAIRandom(100)<20)
          end
        end
      end
    end
    if !pbCanChooseMove?(index,0,false) &&
       !pbCanChooseMove?(index,1,false) &&
       !pbCanChooseMove?(index,2,false) &&
       !pbCanChooseMove?(index,3,false) &&
       @battlers[index].turncount &&
       @battlers[index].turncount>5
      shouldswitch=true
    end
    if skill>=PBTrainerAI.highSkill && @battlers[index].effects[PBEffects::PerishSong]!=1
      for i in 0...4
        move=@battlers[index].moves[i]
        if move.id!=0 && pbCanChooseMove?(index,i,false) &&
          move.function==0xED # Baton Pass
          batonpass=i
          break
        end
      end
    end
    if skill>=PBTrainerAI.highSkill
      if @battlers[index].status==PBStatuses::POISON &&
         @battlers[index].statusCount>0
        toxicHP=(@battlers[index].totalhp/16)
        nextToxicHP=toxicHP*(@battlers[index].effects[PBEffects::Toxic]+1)
        if nextToxicHP>=@battlers[index].hp &&
           toxicHP<@battlers[index].hp && pbAIRandom(100)<80
          shouldswitch=true
        end
      end
    end
    if skill>=PBTrainerAI.mediumSkill
      if @battlers[index].effects[PBEffects::Encore]>0
        scoreSum=0
        scoreCount=0
        attacker=@battlers[index]
        encoreIndex=@battlers[index].effects[PBEffects::EncoreIndex]
        if !attacker.pbOpposing1.fainted?
          scoreSum+=pbGetMoveScore(attacker.moves[encoreIndex],
             attacker,attacker.pbOpposing1,skill)
          scoreCount+=1
        end
        if !attacker.pbOpposing2.fainted?
          scoreSum+=pbGetMoveScore(attacker.moves[encoreIndex],
             attacker,attacker.pbOpposing2,skill)
          scoreCount+=1
        end
        if scoreCount>0 && scoreSum/scoreCount<=20 && pbAIRandom(10)<8
          shouldswitch=true
        end
      end
    end
    if skill>=PBTrainerAI.highSkill
      if !@doublebattle && !@battlers[index].pbOppositeOpposing.fainted? 
        opp=@battlers[index].pbOppositeOpposing
        if (opp.effects[PBEffects::HyperBeam]>0 ||
           (opp.hasWorkingAbility(:TRUANT) &&
           opp.effects[PBEffects::Truant])) && pbAIRandom(100)<80
          shouldswitch=false
        end
      end
    end
    if @rules["suddendeath"]
      if @battlers[index].hp<=(@battlers[index].totalhp/4) && pbAIRandom(10)<3 && 
         @battlers[index].turncount>0
        shouldswitch=true
      elsif @battlers[index].hp<=(@battlers[index].totalhp/2) && pbAIRandom(10)<8 && 
         @battlers[index].turncount>0
        shouldswitch=true
      end
    end
    if @battlers[index].effects[PBEffects::PerishSong]==1
      shouldswitch=true
    end
    if shouldswitch
      list=[]
      party=pbParty(index)
      for i in 0...party.length
        if pbCanSwitch?(index,i,false)
          # If perish count is 1, it may be worth it to switch
          # even with Spikes, since Perish Song's effect will end
          if @battlers[index].effects[PBEffects::PerishSong]!=1
            # Will contain effects that recommend against switching
            spikes=@battlers[index].pbOwnSide.effects[PBEffects::Spikes]
            if (spikes==1 && party[i].hp<=(party[i].totalhp/8)) ||
               (spikes==2 && party[i].hp<=(party[i].totalhp/6)) ||
               (spikes==3 && party[i].hp<=(party[i].totalhp/4))
              if !party[i].hasType?(:FLYING) &&
                 !party[i].hasWorkingAbility(:LEVITATE)
                # Don't switch to this if too little HP
                next
              end
            end
          end
          if movetype>=0 && pbTypeModifier(movetype,@battlers[index],@battlers[index])==0
            weight=65
            if pbTypeModifier2(party[i],@battlers[index].pbOppositeOpposing)>8
              # Greater weight if new Pokemon's type is effective against opponent
              weight=85
            end
            if pbAIRandom(100)<weight
              list.unshift(i) # put this Pokemon first
            end
          elsif movetype>=0 && pbTypeModifier(movetype,@battlers[index],@battlers[index])<8
            weight=40
            if pbTypeModifier2(party[i],@battlers[index].pbOppositeOpposing)>8
              # Greater weight if new Pokemon's type is effective against opponent
              weight=60
            end
            if pbAIRandom(100)<weight
              list.unshift(i) # put this Pokemon first
            end
          else
            list.push(i) # put this Pokemon last
          end
        end
      end
      if list.length>0
        if batonpass!=-1
          if !pbRegisterMove(index,batonpass,false)
            return pbRegisterSwitch(index,list[0])
          end
          return true
        else
          return pbRegisterSwitch(index,list[0])
        end
      end
    end
    return false
  end

  def pbDefaultChooseNewEnemy(index,party)
    enemies=[]
    for i in 0..party.length-1
      if pbCanSwitchLax?(index,i,false)
        enemies.push(i)
      end
    end
    if enemies.length>0
      return pbChooseBestNewEnemy(index,party,enemies)
    end
    return -1
  end

  def pbChooseBestNewEnemy(index,party,enemies)
    return -1 if !enemies || enemies.length==0
    $PokemonTemp=PokemonTemp.new if !$PokemonTemp
    o1=@battlers[index].pbOpposing1
    o2=@battlers[index].pbOpposing2
    o1=nil if o1 && o1.fainted?
    o2=nil if o2 && o2.fainted?
    best=-1
    bestSum=0
    for e in enemies
      pkmn=party[e]
      sum=0
      for move in pkmn.moves
        next if move.id==0
        md=PBMoveData.new(move.id)
        next if md.basedamage==0
        if o1
          sum+=PBTypes.getCombinedEffectiveness(md.type,o1.type1,o1.type2,o1.effects[PBEffects::Type3])
        end
        if o2
          sum+=PBTypes.getCombinedEffectiveness(md.type,o2.type1,o2.type2,o2.effects[PBEffects::Type3])
        end
      end
      if best==-1 || sum>bestSum
        best=e
        bestSum=sum
      end
    end
    return best
  end

################################################################################
# Choose an action.
################################################################################
  def pbDefaultChooseEnemyCommand(index)
    if !pbCanShowFightMenu?(index)
      return if pbEnemyShouldUseItem?(index)
      return if pbEnemyShouldWithdraw?(index)
      pbAutoChooseMove(index)
      return
    else
      return if pbEnemyShouldUseItem?(index)
      return if pbEnemyShouldWithdraw?(index)
      return if pbAutoFightMenu(index)
      pbRegisterMegaEvolution(index) if pbEnemyShouldMegaEvolve?(index)
      pbChooseMoves(index)
    end
  end

################################################################################
# Other functions.
################################################################################
  def pbDbgPlayerOnly?(idx)
    return true if !$INTERNAL
    return pbOwnedByPlayer?(idx.index) if idx.respond_to?("index")
    return pbOwnedByPlayer?(idx)
  end

  def pbStdDev(scores)
    n=0
    sum=0
    scores.each{|s| sum+=s; n+=1 }
    return 0 if n==0
    mean=sum.to_f/n.to_f
    varianceTimesN=0
    for i in 0...scores.length
      if scores[i]>0
        deviation=scores[i].to_f-mean
        varianceTimesN+=deviation*deviation
      end
    end
    # Using population standard deviation 
    # [(n-1) makes it a sample std dev, would be 0 with only 1 sample]
    return Math.sqrt(varianceTimesN/n)
  end
end