# Loads data from a file "safely", similar to load_data. If an encrypted archive
# exists, the real file is deleted to ensure that the file is loaded from the
# encrypted archive.
def pbSafeLoad(file)
  if (safeExists?("./Game.rgssad") || safeExists?("./Game.rgss2a")) && safeExists?(file)
    File.delete(file) rescue nil
  end
  return load_data(file)
end

def pbLoadRxData(file) # :nodoc:
  if $RPGVX
    return load_data(file+".rvdata")
  else
    return load_data(file+".rxdata") 
  end
end

def pbChooseLanguage
  commands=[]
  for lang in LANGUAGES
    commands.push(lang[0])
  end
  return Kernel.pbShowCommands(nil,commands)
end

if !Kernel.respond_to?("pbSetResizeFactor")
  def pbSetResizeFactor(dummy,dummy2=false); end
  def setScreenBorderName(border); end

  $ResizeFactor    = 1.0
  $ResizeFactorMul = 100
  $ResizeOffsetX   = 0
  $ResizeOffsetY   = 0
  $ResizeFactorSet = false

  module Graphics
    def self.snap_to_bitmap; return nil; end
  end
end


#############
#############


def pbSetUpSystem
  begin
    trainer=nil
    framecount=0
    havedata=false
    game_system=nil
    pokemonSystem=nil
    File.open(RTP.getSaveFileName("Game.rxdata")){|f|
       trainer=Marshal.load(f)
       framecount=Marshal.load(f)
       game_system=Marshal.load(f)
       pokemonSystem=Marshal.load(f)
    }
    raise "Corrupted file" if !trainer.is_a?(PokeBattle_Trainer)
    raise "Corrupted file" if !framecount.is_a?(Numeric)
    raise "Corrupted file" if !game_system.is_a?(Game_System)
    raise "Corrupted file" if !pokemonSystem.is_a?(PokemonSystem)
    havedata=true
  rescue
    pokemonSystem=PokemonSystem.new
    game_system=Game_System.new
  end
  if !$INEDITOR
    $PokemonSystem=pokemonSystem
    $game_system=Game_System
    pbSetResizeFactor($PokemonSystem.screensize)
  else
    pbSetResizeFactor(1.0)
  end
  # Load constants
  begin
    consts=pbSafeLoad("Data/Constants.rxdata")
    consts=[] if !consts
  rescue
    consts=[]
  end
  for script in consts
    next if !script
    eval(Zlib::Inflate.inflate(script[2]),nil,script[1])
  end
  if LANGUAGES.length>=2
    if !havedata
      pokemonSystem.language=pbChooseLanguage
    end
    pbLoadMessages("Data/"+LANGUAGES[pokemonSystem.language][1])
  end
end

def pbScreenCapture
  capturefile=nil
  5000.times {|i|
     filename=RTP.getSaveFileName(sprintf("capture%03d.bmp",i))
     if !safeExists?(filename)
       capturefile=filename
       break
     end
     i+=1
  }
  if capturefile && safeExists?("rubyscreen.dll")
    takescreen=Win32API.new("rubyscreen.dll","TakeScreenshot","%w(p)","i")
    takescreen.call(capturefile)
    if safeExists?(capturefile)
      pbSEPlay("expfull") if FileTest.audio_exist?("Audio/SE/expfull")
    end
  end
end



module Input
  unless defined?(update_KGC_ScreenCapture)
    class << Input
      alias update_KGC_ScreenCapture update
    end
  end

  def self.update
    update_KGC_ScreenCapture
    if trigger?(Input::F8)
      pbScreenCapture
    end
    if trigger?(Input::F7)
      pbDebugF7
    end
  end
end



def pbDebugF7
  if $DEBUG
    Console::setup_console
    begin
      debugBitmaps
    rescue
    end
    pbSEPlay("expfull") if FileTest.audio_exist?("Audio/SE/expfull")
  end
end

pbSetUpSystem()