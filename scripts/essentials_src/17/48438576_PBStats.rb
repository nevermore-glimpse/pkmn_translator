begin
  module PBStats
    HP       = 0
    ATTACK   = 1
    DEFENSE  = 2
    SPEED    = 3
    SPATK    = 4
    SPDEF    = 5
    ACCURACY = 6
    EVASION  = 7

    def PBStats.getName(id)
      names = [
         _INTL("HP"),
         _INTL("Attack"),
         _INTL("Defense"),
         _INTL("Speed"),
         _INTL("Special Attack"),
         _INTL("Special Defense"),
         _INTL("accuracy"),
         _INTL("evasiveness")
      ]
      return names[id]
    end
    def PBStats.getNameBrief(id)
      names = [
         _INTL("HP"),
         _INTL("Atk"),
         _INTL("Def"),
         _INTL("Spd"),
         _INTL("SpAtk"),
         _INTL("SpDef"),
         _INTL("acc"),
         _INTL("eva")
      ]
      return names[id]
    end  end

rescue Exception
  if $!.is_a?(SystemExit) || "#{$!.class}"=="Reset"
    raise $!
  end
end