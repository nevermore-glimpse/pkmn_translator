begin
  module PBEnvironment
    None        = 0
    Grass       = 1
    TallGrass   = 2
    MovingWater = 3
    StillWater  = 4
    Underwater  = 5
    Cave        = 6
    Rock        = 7
    Sand        = 8
    Forest      = 9
    Snow        = 10
    Volcano     = 11
    Graveyard   = 12
    Sky         = 13
    Space       = 14
  end

rescue Exception
  if $!.is_a?(SystemExit) || "#{$!.class}"=="Reset"
    raise $!
  end
end