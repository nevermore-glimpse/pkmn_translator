#70925035
begin
  module PBStatuses
    SLEEP     = 1
    POISON    = 2
    BURN      = 3
    PARALYSIS = 4
    FROZEN    = 5

    def PBStatuses.getName(id)
      names = [
         _INTL("healthy"),
         _INTL("asleep"),
         _INTL("poisoned"),
         _INTL("burned"),
         _INTL("paralyzed"),
         _INTL("frozen")
      ]
      return names[id]
    end  end

rescue Exception
  if $!.is_a?(SystemExit) || "#{$!.class}"=="Reset"
    raise $!
  end
end