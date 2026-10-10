#===============================================================================
# Terrain tags
#===============================================================================
module PBTerrain
  Ledge           = 1
  Grass           = 2
  Sand            = 3
  Rock            = 4
  DeepWater       = 5
  StillWater      = 6
  Water           = 7
  Waterfall       = 8
  WaterfallCrest  = 9
  TallGrass       = 10
  UnderwaterGrass = 11
  Ice             = 12
  Neutral         = 13
  SootGrass       = 14
  Bridge          = 15
  Puddle          = 16

  def PBTerrain.isSurfable?(tag)
    return PBTerrain.isWater?(tag)
  end

  def PBTerrain.isWater?(tag)
    return tag==PBTerrain::Water ||
           tag==PBTerrain::StillWater ||
           tag==PBTerrain::DeepWater ||
           tag==PBTerrain::WaterfallCrest ||
           tag==PBTerrain::Waterfall
  end

  def PBTerrain.isPassableWater?(tag)
    return tag==PBTerrain::Water ||
           tag==PBTerrain::StillWater ||
           tag==PBTerrain::DeepWater ||
           tag==PBTerrain::WaterfallCrest
  end

  def PBTerrain.isJustWater?(tag)
    return tag==PBTerrain::Water ||
           tag==PBTerrain::StillWater ||
           tag==PBTerrain::DeepWater
  end

  def PBTerrain.isDeepWater?(tag)
    return tag==PBTerrain::DeepWater
  end

  def PBTerrain.isWaterfall?(tag)
    return tag==PBTerrain::WaterfallCrest ||
           tag==PBTerrain::Waterfall
  end

  def PBTerrain.isGrass?(tag)
    return tag==PBTerrain::Grass ||
           tag==PBTerrain::TallGrass ||
           tag==PBTerrain::UnderwaterGrass ||
           tag==PBTerrain::SootGrass
  end

  def PBTerrain.isJustGrass?(tag)   # The Poké Radar only works in these tiles
    return tag==PBTerrain::Grass ||
           tag==PBTerrain::SootGrass
  end

  def PBTerrain.isLedge?(tag)
    return tag==PBTerrain::Ledge
  end

  def PBTerrain.isIce?(tag)
    return tag==PBTerrain::Ice
  end

  def PBTerrain.isBridge?(tag)
    return tag==PBTerrain::Bridge
  end

  def PBTerrain.hasReflections?(tag)
    return tag==PBTerrain::StillWater ||
           tag==PBTerrain::Puddle
  end

  def PBTerrain.onlyWalk?(tag)
    return tag==PBTerrain::TallGrass ||
           tag==PBTerrain::Ice
  end

  def PBTerrain.isDoubleWildBattle?(tag)
    return tag==PBTerrain::TallGrass
  end
end