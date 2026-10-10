begin
  class PokeBattle_ActiveSide
    attr_accessor :effects

    def initialize
      @effects = []
      @effects[PBEffects::CraftyShield]       = false
      @effects[PBEffects::EchoedVoiceCounter] = 0
      @effects[PBEffects::EchoedVoiceUsed]    = false
      @effects[PBEffects::LastRoundFainted]   = -1
      @effects[PBEffects::LightScreen]        = 0
      @effects[PBEffects::LuckyChant]         = 0
      @effects[PBEffects::MatBlock]           = false
      @effects[PBEffects::Mist]               = 0
      @effects[PBEffects::QuickGuard]         = false
      @effects[PBEffects::Rainbow]            = 0
      @effects[PBEffects::Reflect]            = 0
      @effects[PBEffects::Round]              = 0
      @effects[PBEffects::Safeguard]          = 0
      @effects[PBEffects::SeaOfFire]          = 0
      @effects[PBEffects::Spikes]             = 0
      @effects[PBEffects::StealthRock]        = false
      @effects[PBEffects::StickyWeb]          = false
      @effects[PBEffects::Swamp]              = 0
      @effects[PBEffects::Tailwind]           = 0
      @effects[PBEffects::ToxicSpikes]        = 0
      @effects[PBEffects::WideGuard]          = false
    end
  end



  class PokeBattle_ActiveField
    attr_accessor :effects

    def initialize
      @effects = []
      @effects[PBEffects::ElectricTerrain] = 0
      @effects[PBEffects::FairyLock]       = 0
      @effects[PBEffects::FusionBolt]      = false
      @effects[PBEffects::FusionFlare]     = false
      @effects[PBEffects::GrassyTerrain]   = 0
      @effects[PBEffects::Gravity]         = 0
      @effects[PBEffects::IonDeluge]       = false
      @effects[PBEffects::MagicRoom]       = 0
      @effects[PBEffects::MistyTerrain]    = 0
      @effects[PBEffects::MudSportField]   = 0
      @effects[PBEffects::TrickRoom]       = 0
      @effects[PBEffects::WaterSportField] = 0
      @effects[PBEffects::WonderRoom]      = 0
    end
  end

rescue Exception
  if $!.is_a?(SystemExit) || "#{$!.class}"=="Reset"
    raise $!
  end
end