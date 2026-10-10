#===============================================================================
# * Egg Hatch Animation - by FL (Credits will be apreciated)
#                         Tweaked by Maruno
#===============================================================================
# This script is for Pokémon Essentials. It's an egg hatch animation that
# works even with special eggs like Manaphy egg.
#===============================================================================
# To this script works, put it above Main and put a picture (a 5 frames
# sprite sheet) with egg sprite height and 5 times the egg sprite width at
# Graphics/Battlers/eggCracks.
#===============================================================================
class PokemonEggHatch_Scene
  def pbStartScene(pokemon)
    @sprites={}
    @pokemon=pokemon
    @nicknamed=false
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z=99999
    addBackgroundOrColoredPlane(@sprites,"background","hatchbg",
       Color.new(248,248,248),@viewport)
    @sprites["pokemon"]=PokemonSprite.new(@viewport)
    @sprites["pokemon"].setOffset(PictureOrigin::Bottom)
    @sprites["pokemon"].x = Graphics.width/2
    @sprites["pokemon"].y = 264+56 # 56 to offset the egg sprite
    @sprites["pokemon"].setSpeciesBitmap(@pokemon.species,@pokemon.isFemale?,
                                         (@pokemon.form rescue 0),@pokemon.isShiny?,
                                         false,false,true) # Egg sprite
    @sprites["hatch"]=BitmapSprite.new(Graphics.width,Graphics.height,@viewport)
    @sprites["overlay"]=BitmapSprite.new(Graphics.width,Graphics.height,@viewport)
    @sprites["overlay"].z=200
    @sprites["overlay"].bitmap=Bitmap.new(Graphics.width,Graphics.height)
    @sprites["overlay"].bitmap.fill_rect(0,0,Graphics.width,Graphics.height,
        Color.new(255,255,255))
    @sprites["overlay"].opacity=0
    pbFadeInAndShow(@sprites)
  end

  def pbMain
    crackfilename=sprintf("Graphics/Battlers/%seggCracks",getConstantName(PBSpecies,@pokemon.species)) rescue nil
    if !pbResolveBitmap(crackfilename)
      crackfilename=sprintf("Graphics/Battlers/%03deggCracks",@pokemon.species)
      if !pbResolveBitmap(crackfilename)
        crackfilename=sprintf("Graphics/Battlers/eggCracks")
      end
    end
    crackfilename=pbResolveBitmap(crackfilename)
    hatchSheet=AnimatedBitmap.new(crackfilename)
    pbBGMPlay("Evolution")
    # Egg animation
    updateScene(60)
    pbPositionHatchMask(hatchSheet,0)
    pbSEPlay("Battle ball shake")
    swingEgg(2)
    updateScene(8)
    pbPositionHatchMask(hatchSheet,1)
    pbSEPlay("Battle ball shake")
    swingEgg(2)
    updateScene(16)
    pbPositionHatchMask(hatchSheet,2)
    pbSEPlay("Battle ball shake")
    swingEgg(4,2)
    updateScene(16)
    pbPositionHatchMask(hatchSheet,3)
    pbSEPlay("Battle ball shake")
    swingEgg(8,4)
    updateScene(8)
    pbPositionHatchMask(hatchSheet,4)
    pbSEPlay("Battle recall")
    # Fade and change the sprite
    fadeSpeed=15
    for i in 1..(255/fadeSpeed)
      @sprites["pokemon"].tone=Tone.new(i*fadeSpeed,i*fadeSpeed,i*fadeSpeed)
      @sprites["overlay"].opacity=i*fadeSpeed
      updateScene
    end
    updateScene(30)
    @sprites["pokemon"].setPokemonBitmap(@pokemon) # Pokémon sprite
    metrics=load_data("Data/metrics.dat")
    @sprites["pokemon"].y = 264
    @sprites["pokemon"].y += (metrics[1][@pokemon.species] || 0)*2 - (metrics[2][@pokemon.species] || 0)*2
    @sprites["hatch"].visible=false
    for i in 1..(255/fadeSpeed)
      @sprites["pokemon"].tone=Tone.new(255-i*fadeSpeed,255-i*fadeSpeed,255-i*fadeSpeed)
      @sprites["overlay"].opacity=255-i*fadeSpeed
      updateScene
    end
    @sprites["pokemon"].tone=Tone.new(0,0,0)
    @sprites["overlay"].opacity=0
    # Finish scene
    frames=pbCryFrameLength(@pokemon)
    pbPlayCry(@pokemon)
    updateScene(frames)
    pbBGMStop()
    pbMEPlay("Evolution success")
    Kernel.pbMessage(_INTL("\\se[]{1} hatched from the Egg!\\wt[80]",@pokemon.name)) { update }
    if Kernel.pbConfirmMessage(
        _INTL("Would you like to nickname the newly hatched {1}?",@pokemon.name)) { update }
      nickname=pbEnterPokemonName(_INTL("{1}'s nickname?",@pokemon.name),
         0,PokeBattle_Pokemon::NAMELIMIT,"",@pokemon,true)
      @pokemon.name=nickname if nickname!=""
      @nicknamed=true
    end
  end

  def pbPositionHatchMask(hatchSheet,index)
    @sprites["hatch"].bitmap.clear
    frames = 5
    frameWidth = (hatchSheet.width/frames).floor
    rect = Rect.new(frameWidth*index,0,frameWidth,hatchSheet.height)
    @sprites["hatch"].bitmap.blt(
       @sprites["pokemon"].x-@sprites["pokemon"].bitmap.width/2,
       @sprites["pokemon"].y-@sprites["pokemon"].bitmap.height,
       hatchSheet.bitmap,rect)
  end

  def swingEgg(speed,swingTimes=1) # Only accepts 2, 4 or 8 for speed.
    limit = 8
    targets = [@sprites["pokemon"].x-limit,@sprites["pokemon"].x+limit,
               @sprites["pokemon"].x]
    swingTimes.times do
      usedSpeed=speed
      for target in targets
        usedSpeed*=-1
        while target!=@sprites["pokemon"].x
          @sprites["pokemon"].x+=usedSpeed
          @sprites["hatch"].x+=usedSpeed
          updateScene
        end
      end
    end
  end

  def updateScene(frames=1) # Can be used for "wait" effect
    frames.times do
      Graphics.update
      Input.update
      self.update
    end
  end  

  def update
    pbUpdateSpriteHash(@sprites)
  end

  def pbEndScene
    pbFadeOutAndHide(@sprites) { update } if !@nicknamed
    pbDisposeSpriteHash(@sprites)
    @viewport.dispose
  end
end



class PokemonEggHatchScreen
  def initialize(scene)
    @scene=scene
  end

  def pbStartScreen(pokemon)
    @scene.pbStartScene(pokemon)
    @scene.pbMain
    @scene.pbEndScene
  end
end



def pbHatchAnimation(pokemon)
  Kernel.pbMessage(_INTL("Huh?\1"))
  pbFadeOutInWithMusic(99999) {
    scene=PokemonEggHatch_Scene.new
    screen=PokemonEggHatchScreen.new(scene)
    screen.pbStartScreen(pokemon)
  }
  return true
end

def pbHatch(pokemon)
  speciesname = PBSpecies.getName(pokemon.species)
  pokemon.name           = speciesname
  pokemon.trainerID      = $Trainer.id
  pokemon.ot             = $Trainer.name
  pokemon.happiness      = 120
  pokemon.timeEggHatched = pbGetTimeNow
  pokemon.obtainMode     = 1   # hatched from egg
  pokemon.hatchedMap     = $game_map.map_id
  $Trainer.seen[pokemon.species]  = true
  $Trainer.owned[pokemon.species] = true
  pbSeenForm(pokemon)
  pokemon.pbRecordFirstMoves
  if !pbHatchAnimation(pokemon)
    Kernel.pbMessage(_INTL("Huh?\1"))
    Kernel.pbMessage(_INTL("...\1"))
    Kernel.pbMessage(_INTL("... .... .....\1"))
    Kernel.pbMessage(_INTL("{1} hatched from the Egg!",speciesname))
    if Kernel.pbConfirmMessage(_INTL("Would you like to nickname the newly hatched {1}?",speciesname))
      species=PBSpecies.getName(pokemon.species)
      nickname=pbEnterPokemonName(_INTL("{1}'s nickname?",speciesname),
         0,PokeBattle_Pokemon::NAMELIMIT,"",pokemon)
      pokemon.name=nickname if nickname!=""
    end
  end
end

Events.onStepTaken+=proc {|sender,e|
  next if !$Trainer
  for egg in $Trainer.party
    if egg.eggsteps>0
      egg.eggsteps-=1
      for i in $Trainer.pokemonParty
        if isConst?(i.ability,PBAbilities,:FLAMEBODY) ||
           isConst?(i.ability,PBAbilities,:MAGMAARMOR)
          egg.eggsteps-=1
          break
        end
      end
      if egg.eggsteps<=0
        egg.eggsteps=0
        pbHatch(egg)
      end
    end
  end
}