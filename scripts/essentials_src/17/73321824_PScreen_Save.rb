def pbSave(safesave=false)
  $Trainer.metaID=$PokemonGlobal.playerID
  begin
    File.open(RTP.getSaveFileName("Game.rxdata"),"wb"){|f|
       Marshal.dump($Trainer,f)
       Marshal.dump(Graphics.frame_count,f)
       if $data_system.respond_to?("magic_number")
         $game_system.magic_number = $data_system.magic_number
       else
         $game_system.magic_number = $data_system.version_id
       end
       $game_system.save_count+=1
       Marshal.dump($game_system,f)
       Marshal.dump($PokemonSystem,f)
       Marshal.dump($game_map.map_id,f)
       Marshal.dump($game_switches,f)
       Marshal.dump($game_variables,f)
       Marshal.dump($game_self_switches,f)
       Marshal.dump($game_screen,f)
       Marshal.dump($MapFactory,f)
       Marshal.dump($game_player,f)
       $PokemonGlobal.safesave=safesave
       Marshal.dump($PokemonGlobal,f)
       Marshal.dump($PokemonMap,f)
       Marshal.dump($PokemonBag,f)
       Marshal.dump($PokemonStorage,f)
    }
    Graphics.frame_reset
  rescue
    return false
  end
  return true
end

def pbEmergencySave
  oldscene=$scene
  $scene=nil
  Kernel.pbMessage(_INTL("The script is taking too long. The game will restart."))
  return if !$Trainer
  if safeExists?(RTP.getSaveFileName("Game.rxdata"))
    File.open(RTP.getSaveFileName("Game.rxdata"),  'rb') {|r|
      File.open(RTP.getSaveFileName("Game.rxdata.bak"), 'wb') {|w|
        while s = r.read(4096)
          w.write s
        end
      }
    }
  end
  if pbSave
    Kernel.pbMessage(_INTL("\\se[]The game was saved.\\me[GUI save game]\\wtnp[30]"))
  else
    Kernel.pbMessage(_INTL("\\se[]Save failed.\\wtnp[30]"))
  end
  $scene=oldscene
end



class PokemonSave_Scene
  def pbStartScreen
    @viewport=Viewport.new(0,0,Graphics.width,Graphics.height)
    @viewport.z=99999
    @sprites={}
    totalsec = Graphics.frame_count / Graphics.frame_rate
    hour = totalsec / 60 / 60
    min = totalsec / 60 % 60
    mapname=$game_map.name
    textColor=["0070F8,78B8E8","E82010,F8A8B8","0070F8,78B8E8"][$Trainer.gender]
    loctext=_INTL("<ac><c2=06644bd2>{1}</c2></ac>",mapname)
    loctext+=_INTL("Player<r><c3={1}>{2}</c3><br>",textColor,$Trainer.name)
    loctext+=_ISPRINTF("Time<r><c3={1:s}>{2:02d}:{3:02d}</c3><br>",textColor,hour,min)
    loctext+=_INTL("Badges<r><c3={1}>{2}</c3><br>",textColor,$Trainer.numbadges)
    if $Trainer.pokedex
      loctext+=_INTL("Pokédex<r><c3={1}>{2}/{3}</c3>",textColor,$Trainer.pokedexOwned,$Trainer.pokedexSeen)
    end
    @sprites["locwindow"]=Window_AdvancedTextPokemon.new(loctext)
    @sprites["locwindow"].viewport=@viewport
    @sprites["locwindow"].x=0
    @sprites["locwindow"].y=0
    @sprites["locwindow"].width=228 if @sprites["locwindow"].width<228
    @sprites["locwindow"].visible=true
  end

  def pbEndScreen
    pbDisposeSpriteHash(@sprites)
    @viewport.dispose
  end
end



class PokemonSaveScreen
  def initialize(scene)
    @scene=scene
  end

  def pbDisplay(text,brief=false)
    @scene.pbDisplay(text,brief)
  end

  def pbDisplayPaused(text)
    @scene.pbDisplayPaused(text)
  end

  def pbConfirm(text)
    return @scene.pbConfirm(text)
  end

  def pbSaveScreen
    ret=false
    @scene.pbStartScreen
    if Kernel.pbConfirmMessage(_INTL("Would you like to save the game?"))
      if safeExists?(RTP.getSaveFileName("Game.rxdata"))
        confirm=""
        if $PokemonTemp.begunNewGame
          Kernel.pbMessage(_INTL("WARNING!"))
          Kernel.pbMessage(_INTL("There is a different game file that is already saved."))
          Kernel.pbMessage(_INTL("If you save now, the other file's adventure, including items and Pokémon, will be entirely lost."))
          if !Kernel.pbConfirmMessageSerious(
             _INTL("Are you sure you want to save now and overwrite the other save file?"))
            @scene.pbEndScreen
            return false
          end
        end
      end
      $PokemonTemp.begunNewGame=false
      if pbSave
        Kernel.pbMessage(_INTL("\\se[]{1} saved the game.\\me[GUI save game]\\wtnp[30]",$Trainer.name))
        ret=true
      else
        Kernel.pbMessage(_INTL("\\se[]Save failed.\\wtnp[30]"))
        ret=false
      end
    end
    @scene.pbEndScreen
    return ret
  end
end



def pbSaveScreen
  scene = PokemonSave_Scene.new
  screen = PokemonSaveScreen.new(scene)
  ret = screen.pbSaveScreen
  return ret
end