module PBEggGroups
  Monster      = 1
  Water1       = 2
  Bug          = 3
  Flying       = 4
  Field        = 5 # Ground
  Fairy        = 6
  Grass        = 7 # Plant
  Humanlike    = 8 # Humanoid, Humanshape, Human
  Water3       = 9
  Mineral      = 10
  Amorphous    = 11 # Indeterminate
  Water2       = 12
  Ditto        = 13
  Dragon       = 14
  Undiscovered = 15 # NoEggs, None, NA

  def PBEggGroups.maxValue; 15; end
  def PBEggGroups.getCount; 15; end

  def PBEggGroups.getName(id)
    names=["",
       _INTL("Monster"),
       _INTL("Water 1"),
       _INTL("Bug"),
       _INTL("Flying"),
       _INTL("Field"),
       _INTL("Fairy"),
       _INTL("Grass"),
       _INTL("Human-like"),
       _INTL("Water 3"),
       _INTL("Mineral"),
       _INTL("Amorphous"),
       _INTL("Water 2"),
       _INTL("Ditto"),
       _INTL("Dragon"),
       _INTL("Undiscovered")
    ]
    return names[id]
  end
end