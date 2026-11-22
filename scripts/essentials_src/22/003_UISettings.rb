#===============================================================================
#
#===============================================================================
module Settings
  # Whether a move's power/type/category/etc. as shown in battle, the summary
  # screen and the Move Reminder screen will appear as their calculated values
  # (true) or their values from the PBS file moves.txt (false). For example, if
  # this is true, Judgment's displayed type will depend on the Plate being held
  # by the Pokémon that knows it.
  SHOW_MODIFIED_MOVE_PROPERTIES = false

  #-----------------------------------------------------------------------------
  # Pause menu.
  #-----------------------------------------------------------------------------

  # Whether "Town Map" will show as an option in the pause menu if the player
  # has that item in the Bag and doesn't have a Pokégear.
  SHOW_TOWN_MAP_IN_PAUSE_MENU = true

  #-----------------------------------------------------------------------------
  # Pokédex.
  #-----------------------------------------------------------------------------

  # Whether all forms of a given species will be immediately available to view
  # in the Pokédex so long as that species has been seen at all (true), or
  # whether each form needs to be seen specifically before that form appears in
  # the Pokédex (false).
  POKEDEX_SHOWS_ALL_FORMS       = false
  # Whether the Forms page of the Pokédex entry lists (seen) shiny variants of
  # the available forms.
  SHOW_SHINY_SPRITES_IN_POKEDEX = true

  #-----------------------------------------------------------------------------
  # Pokémon summary.
  #-----------------------------------------------------------------------------

  # Whether the player is allowed to rename a Pokémon while looking at its
  # summary screen.
  ALLOW_RENAMING_POKEMON_IN_SUMMARY_SCREEN = (MECHANICS_GENERATION >= 9)
  # Whether the player is allowed to make a Pokémon forget moves and remember
  # moves at will while looking at its summary screen.
  ALLOW_CHANGING_MOVES_IN_SUMMARY_SCREEN   = (MECHANICS_GENERATION >= 9)

  #-----------------------------------------------------------------------------
  # Town Map.
  #-----------------------------------------------------------------------------

  # A set of arrays, each containing details of a graphic to be shown on the
  # region map if appropriate. The values for each array are as follows:
  #   * Region number.
  #   * Game Switch; the graphic is shown if this is ON (non-wall maps only).
  #   * X coordinate of the graphic on the map, in squares.
  #   * Y coordinate of the graphic on the map, in squares.
  #   * Name of the graphic, found in the Graphics/UI/Town Map folder.
  #   * The graphic will always (true) or never (false) be shown on a wall map.
  REGION_MAP_EXTRAS = [
    [0, 51, 16, 15, "hidden_Berth", false],
    [0, 52, 20, 14, "hidden_Faraday", false]
  ]
  # Whether the player can use Fly while looking at the Town Map. This is only
  # allowed if the player can use Fly normally.
  CAN_FLY_FROM_TOWN_MAP               = true
  # Whether pressing Use in the Town Map will zoom it in to 200% and show a text
  # pane on the right showing the selected point's description. The cursor can
  # still be moved while zoomed in.
  ENABLE_TOWN_MAP_ZOOM_IN_FOR_DETAILS = true
  # Whether points in the Town Map can be marked.
  ENABLE_TOWN_MAP_MARKING             = true

  #-----------------------------------------------------------------------------
  # Item storage.
  #-----------------------------------------------------------------------------

  # Whether the player is prevented from depositing a Key Item, TM or HM into
  # item storage.
  DISABLE_STORING_IMPORTANT_ITEMS = true

  #-----------------------------------------------------------------------------
  # Location signpost.
  #-----------------------------------------------------------------------------

  # Pairs of map IDs, where the location sign isn't shown when moving from one
  # of the maps in a pair to the other (and vice versa). Useful for single long
  # routes/towns that are spread over multiple maps.
  #   e.g. [4,5,16,17,42,43] will be map pairs 4,5 and 16,17 and 42,43.
  # Moving between two maps that have the exact same name won't show the
  # location sign anyway, so you don't need to list those maps here.
  NO_LOCATION_SIGNS = []
  # The filename of a location sign graphic to be used if the map metadata for a
  # map doesn't define one. Make this nil to use the default menu windowskin.
  DEFAULT_LOCATION_SIGN_GRAPHIC = "Pt default"
  # Assigns location sign graphics to text styles (numbers). These are used in
  # class LocationWindow to display the text appropriately for the graphic being
  # used. Style :none is reserved for the "no graphic" style. A filename may
  # instead be an array of [filename, text base color, text shadow color].
  LOCATION_SIGN_GRAPHIC_STYLES = {
    :dp       => [["DP", Color.new(72, 80, 72), Color.new(144, 160, 160)]],
    :hgss     => [["HGSS cave",    Color.new(232, 232, 232), Color.new(120, 144, 160)],
                  ["HGSS city",    Color.new(56, 64, 72),    Color.new(152, 152, 144)],
                  ["HGSS default", Color.new(48, 64, 72),    Color.new(144, 144, 96)],
                  ["HGSS forest",  Color.new(232, 232, 232), Color.new(120, 176, 144)],
                  ["HGSS lake",    Color.new(40, 48, 56),    Color.new(104, 144, 192)],
                  ["HGSS park",    Color.new(40, 48, 56),    Color.new(120, 136, 152)],
                  ["HGSS route",   Color.new(48, 64, 72),    Color.new(136, 136, 104)],
                  ["HGSS sea",     Color.new(216, 240, 248), Color.new(24, 96, 144)],
                  ["HGSS town",    Color.new(48, 56, 64),    Color.new(144, 120, 80)]],
    :platinum => ["Pt cave", "Pt city", "Pt default", "Pt forest", "Pt lake",
                  "Pt park", "Pt route", "Pt sea", "Pt town"]
  }

  #-----------------------------------------------------------------------------
  # Messages.
  #-----------------------------------------------------------------------------

  # Whether the messages in a phone call with a trainer are colored blue or red
  # depending on that trainer's gender. Note that this doesn't apply to contacts
  # whose phone calls are in a Common Event; they will need to be colored
  # manually in their Common Events (if relevant).
  COLOR_PHONE_CALL_MESSAGES_BY_CONTACT_GENDER = true
  # Available speech frames. These are graphic files in "Graphics/Windowskins/".
  SPEECH_WINDOWSKINS = [
    "speech hgss 1",
    "speech hgss 2",
    "speech hgss 3",
    "speech hgss 4",
    "speech hgss 5",
    "speech hgss 6",
    "speech hgss 7",
    "speech hgss 8",
    "speech hgss 9",
    "speech hgss 10",
    "speech hgss 11",
    "speech hgss 12",
    "speech hgss 13",
    "speech hgss 14",
    "speech hgss 15",
    "speech hgss 16",
    "speech hgss 17",
    "speech hgss 18",
    "speech hgss 19",
    "speech hgss 20",
    "speech pl 18"
  ]
  # Available menu frames. These are graphic files in "Graphics/Windowskins/".
  MENU_WINDOWSKINS = [
    "choice 1",
    "choice 2",
    "choice 3",
    "choice 4",
    "choice 5",
    "choice 6",
    "choice 7",
    "choice 8",
    "choice 9",
    "choice 10",
    "choice 11",
    "choice 12",
    "choice 13",
    "choice 14",
    "choice 15",
    "choice 16",
    "choice 17",
    "choice 18",
    "choice 19",
    "choice 20",
    "choice 21",
    "choice 22",
    "choice 23",
    "choice 24",
    "choice 25",
    "choice 26",
    "choice 27",
    "choice 28"
  ]
end
