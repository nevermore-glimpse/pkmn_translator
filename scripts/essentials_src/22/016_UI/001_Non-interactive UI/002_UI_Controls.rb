#==============================================================================
# * Scene_Controls
#------------------------------------------------------------------------------
# Shows a help screen listing the keyboard controls.
# Display with:
#      pbEventScreen(ButtonEventScene)
#==============================================================================
class ButtonEventScene < EventScene
  FADE_DURATION = 8   # In 1/20 of a second

  def initialize(viewport = nil)
    super(viewport)
    Graphics.freeze
    @current_screen = 1
    addImage(0, 0, "Graphics/UI/Controls help/bg")
    @labels = []
    @label_screens = []
    @keys = []
    @key_screens = []

    addImageForScreen(1, 16, 96, "Graphics/UI/Controls help/help_arrows")
    addImageForScreen(1, 48, 258, "Graphics/UI/Controls help/help_use")
    addLabelForScreen(1, 128, 68, 352, _INTL("Use the direction keys to move the main character. You can also use them to select entries and navigate menus."))
    addLabelForScreen(1, 128, 228, 352, _INTL("Used to confirm a choice, interact with people and things, and move through text. (Default: Space)"))

    addImageForScreen(2, 48, 114, "Graphics/UI/Controls help/help_back")
    addImageForScreen(2, 48, 258, "Graphics/UI/Controls help/help_action")
    addLabelForScreen(2, 128, 68, 352, _INTL("Used to exit, cancel a choice, and cancel a mode. While moving around, hold to move at a different speed. (Default: Esc)"))
    addLabelForScreen(2, 128, 228, 352, _INTL("Used to open the Pause Menu. Also has various functions depending on context. (Default: Backspace)"))

    addImageForScreen(3, 48, 96, "Graphics/UI/Controls help/help_quick")
    addImageForScreen(3, 42, 252, "Graphics/UI/Controls help/help_f8")
    addLabelForScreen(3, 128, 68, 352, _INTL("Used to open the Ready Menu. Also used to move up and down quickly in some menus, or between tabs in some cases. (Default: PgUp/PgDn)"))
    addLabelForScreen(3, 128, 228, 352, _INTL("Use to take a screenshot. It goes into the \"Screenshots\" folder in the game's folder."))

    set_up_screen(@current_screen, true)
    # NOTE: I don't know why the fade duration needs to be halved for this.
    Graphics.transition(FADE_DURATION / 2, "")
    # Go to next screen when user presses USE
    onCTrigger.set(method(:pbOnScreenEnd))
  end

  def addLabelForScreen(number, x, y, width, text)
    @labels.push(addLabel(x, y, width, text))
    @label_screens.push(number)
    @picturesprites[@picturesprites.length - 1].opacity = 0
  end

  def addImageForScreen(number, x, y, filename)
    @keys.push(addImage(x, y, filename))
    @key_screens.push(number)
    @picturesprites[@picturesprites.length - 1].opacity = 0
  end

  def set_up_screen(number, initial = false)
    dur = (initial) ? 0 : FADE_DURATION
    @label_screens.each_with_index do |screen, i|
      @labels[i].moveOpacity((screen == number) ? dur : 0, dur, (screen == number) ? 255 : 0)
    end
    @key_screens.each_with_index do |screen, i|
      @keys[i].moveOpacity((screen == number) ? dur : 0, dur, (screen == number) ? 255 : 0)
    end
    pictureWait   # Update event scene with the changes
  end

  def pbOnScreenEnd(scene, *args)
    last_screen = [@label_screens.max, @key_screens.max].max
    if @current_screen >= last_screen
      # End scene
      $game_temp.background_bitmap = Graphics.snap_to_bitmap
      Graphics.freeze
      @viewport.color = Color.black   # Ensure screen is black
      Graphics.transition(FADE_DURATION, "fadetoblack")
      $game_temp.background_bitmap.dispose
      scene.dispose
    else
      # Next screen
      @current_screen += 1
      onCTrigger.clear
      set_up_screen(@current_screen)
      onCTrigger.set(method(:pbOnScreenEnd))
    end
  end
end
