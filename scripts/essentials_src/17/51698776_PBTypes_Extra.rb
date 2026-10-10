class PBTypes
  @@TypeData = nil

  def PBTypes.loadTypeData
    if !@@TypeData
      @@TypeData = load_data("Data/types.dat")
      @@TypeData[0].freeze
      @@TypeData[1].freeze
      @@TypeData[2].freeze
      @@TypeData.freeze
    end
    return @@TypeData
  end

  def PBTypes.isPseudoType?(type)
    return PBTypes.loadTypeData()[0].include?(type)
  end

  def PBTypes.isSpecialType?(type)
    return PBTypes.loadTypeData()[1].include?(type)
  end

  def PBTypes.getEffectiveness(attackType,opponentType)
    return 2 if !opponentType || opponentType<0
    return PBTypes.loadTypeData()[2][attackType*(PBTypes.maxValue+1)+opponentType]
  end

  def PBTypes.getCombinedEffectiveness(attackType,opponentType1,opponentType2=nil,opponentType3=nil)
    mod1 = PBTypes.getEffectiveness(attackType,opponentType1)
    mod2 = 2
    mod3 = 2
    if opponentType2!=nil && opponentType2>=0 && opponentType1!=opponentType2
      mod2 = PBTypes.getEffectiveness(attackType,opponentType2)
    end
    if opponentType3!=nil && opponentType3>=0 &&
       opponentType1!=opponentType3 && opponentType2!=opponentType3
      mod3 = PBTypes.getEffectiveness(attackType,opponentType3)
    end
    return (mod1*mod2*mod3)
  end

  def PBTypes.isIneffective?(attackType,opponentType1,opponentType2=nil,opponentType3=nil)
    e = PBTypes.getCombinedEffectiveness(attackType,opponentType1,opponentType2,opponentType3)
    return e==0
  end

  def PBTypes.isNotVeryEffective?(attackType,opponentType1,opponentType2=nil,opponentType3=nil)
    e = PBTypes.getCombinedEffectiveness(attackType,opponentType1,opponentType2,opponentType3)
    return e>0 && e<8
  end

  def PBTypes.isNormalEffective?(attackType,opponentType1,opponentType2=nil,opponentType3=nil)
    e = PBTypes.getCombinedEffectiveness(attackType,opponentType1,opponentType2,opponentType3)
    return e==8
  end

  def PBTypes.isSuperEffective?(attackType,opponentType1,opponentType2=nil,opponentType3=nil)
    e = PBTypes.getCombinedEffectiveness(attackType,opponentType1,opponentType2,opponentType3)
    return e>8
  end
end