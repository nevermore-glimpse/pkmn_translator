#11045744
begin
  module PBWeather
    SUNNYDAY    = 1
    RAINDANCE   = 2
    SANDSTORM   = 3
    HAIL        = 4
    HARSHSUN    = 5
    HEAVYRAIN   = 6
    STRONGWINDS = 7
    # Shadow Sky is weather 8
  end

rescue Exception
  if $!.is_a?(SystemExit) || "#{$!.class}"=="Reset"
    raise $!
  end
end