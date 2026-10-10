class PokeBattle_DamageState
  attr_accessor :hplost        # HP lost by opponent, inc. HP lost by a substitute
  attr_accessor :critical      # Critical hit flag
  attr_accessor :calcdamage    # Calculated damage
  attr_accessor :typemod       # Type effectiveness
  attr_accessor :substitute    # A substitute took the damage
  attr_accessor :focusband     # Focus Band used
  attr_accessor :focussash     # Focus Sash used
  attr_accessor :sturdy        # Sturdy ability used
  attr_accessor :endured       # Damage was endured
  attr_accessor :berryweakened # A type-resisting berry was used

  def reset
    @hplost        = 0
    @critical      = false
    @calcdamage    = 0
    @typemod       = 0
    @substitute    = false
    @focusband     = false
    @focussash     = false
    @sturdy        = false
    @endured       = false
    @berryweakened = false
  end

  def initialize
    reset
  end
end



################################################################################
# Success state (used for Battle Arena)
################################################################################
class PokeBattle_SuccessState
  attr_accessor :typemod
  attr_accessor :useState    # 0 - not used, 1 - failed, 2 - succeeded
  attr_accessor :protected
  attr_accessor :skill

  def initialize
    clear
  end

  def clear
    @typemod   = 4
    @useState  = 0
    @protected = false
    @skill     = 0
  end

  def updateSkill
    if @useState==1 && !@protected
      @skill-=2
    elsif @useState==2
      if @typemod>4
        @skill+=2 # "Super effective"
      elsif @typemod>=1 && @typemod<4
        @skill-=1 # "Not very effective"
      elsif @typemod==0
        @skill-=2 # Ineffective
      else
        @skill+=1
      end
    end
    @typemod=4
    @useState=0
    @protected=false
  end
end