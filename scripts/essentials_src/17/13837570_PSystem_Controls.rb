def pbSameThread(wnd)
  return false if wnd==0
  processid = [0].pack('l')
  getCurrentThreadId       = Win32API.new('kernel32','GetCurrentThreadId', '%w()','l')
  getWindowThreadProcessId = Win32API.new('user32','GetWindowThreadProcessId', '%w(l p)','l')
  threadid    = getCurrentThreadId.call
  wndthreadid = getWindowThreadProcessId.call(wnd,processid)
  return (wndthreadid==threadid)
end



module Input
  DOWN   = 2
  LEFT   = 4
  RIGHT  = 6
  UP     = 8
  A      = 11
  B      = 12
  C      = 13
  X      = 14
  Y      = 15
  Z      = 16
  L      = 17
  R      = 18
  SHIFT  = 21
  CTRL   = 22
  ALT    = 23
  F5 = F = 25
  F6     = 26
  F7     = 27
  F8     = 28
  F9     = 29
  LeftMouseKey  = 1
  RightMouseKey = 2
  # GetAsyncKeyState or GetKeyState will work here
  @GetKeyState         = Win32API.new("user32","GetAsyncKeyState","i","i")
  @GetForegroundWindow = Win32API.new("user32","GetForegroundWindow","","i")

  # Returns whether a key is being pressed
  def self.getstate(key)
    return (@GetKeyState.call(key)&0x8000)>0
  end

  def self.updateKeyState(i)
    gfw = pbSameThread(@GetForegroundWindow.call())
    if !@stateUpdated[i]
      newstate = self.getstate(i) && gfw
      @triggerstate[i] = (newstate && @keystate[i]==0)
      @releasestate[i] = (!newstate && @keystate[i]>0)
      @keystate[i] = (newstate) ? @keystate[i]+1 : 0
      @stateUpdated[i] = true
    end
  end

  def self.update
    if @keystate
      for i in 0...256
        # just noting that the state should be updated
        # instead of thunking to Win32 256 times
        @stateUpdated[i] = false
        if @keystate[i]>0
          # If there is a repeat count, update anyway
          # (will normally apply only to a very few keys)
          updateKeyState(i)
        end
      end    
    else
      @stateUpdated = []
      @keystate     = []
      @triggerstate = []
      @releasestate = []
      for i in 0...256
        @stateUpdated[i] = true
        @keystate[i]     = (self.getstate(i)) ? 1 : 0
        @triggerstate[i] = false
        @releasestate[i] = false
      end
    end
  end

  def self.buttonToKey(button)
    case button
    when Input::DOWN;  return [0x28]                # Down
    when Input::LEFT;  return [0x25]                # Left
    when Input::RIGHT; return [0x27]                # Right
    when Input::UP;    return [0x26]                # Up
    when Input::A;     return [0x5A,0x57,0x59,0x10] # Z, W, Y, Shift
    when Input::B;     return [0x58,0x1B]           # X, ESC
    when Input::C;     return [0x43,0x0D,0x20]      # C, ENTER, Space
#    when Input::X;     return [0x41]                # A
#    when Input::Y;     return [0x53]                # S
#    when Input::Z;     return [0x44]                # D
    when Input::L;     return [0x41,0x51,0x21]      # A, Q, Page Up
    when Input::R;     return [0x53,0x22]           # S, Page Down
    when Input::SHIFT; return [0x10]                # Shift
    when Input::CTRL;  return [0x11]                # Ctrl
    when Input::ALT;   return [0x12]                # Alt
    when Input::F5;    return [0x46,0x74,0x09]      # F, F5, Tab
    when Input::F6;    return [0x75]                # F6
    when Input::F7;    return [0x76]                # F7
    when Input::F8;    return [0x77]                # F8
    when Input::F9;    return [0x78]                # F9
    else; return []
    end
  end

  def self.dir4
    button      = 0
    repeatcount = 0
    return 0 if self.press?(Input::DOWN) && self.press?(Input::UP)
    return 0 if self.press?(Input::LEFT) && self.press?(Input::RIGHT)
    for b in [Input::DOWN,Input::LEFT,Input::RIGHT,Input::UP]
      rc = self.count(b)
      if rc>0
        if repeatcount==0 || rc<repeatcount
          button      = b
          repeatcount = rc
        end
      end
    end
    return button
  end

  def self.dir8
    buttons = []
    for b in [Input::DOWN,Input::LEFT,Input::RIGHT,Input::UP]
      rc = self.count(b)
      buttons.push([b,rc]) if rc>0
    end
    if buttons.length==0
      return 0
    elsif buttons.length==1
      return buttons[0][0]
    elsif buttons.length==2
      # since buttons sorted by button, no need to sort here
      return 0 if (buttons[0][0]==Input::DOWN && buttons[1][0]==Input::UP)
      return 0 if (buttons[0][0]==Input::LEFT && buttons[1][0]==Input::RIGHT)
    end
    buttons.sort!{|a,b| a[1]<=>b[1]}
    updown    = 0
    leftright = 0
    for b in buttons
      updown    = b[0] if updown==0 && (b[0]==Input::UP || b[0]==Input::DOWN)
      leftright = b[0] if leftright==0 && (b[0]==Input::LEFT || b[0]==Input::RIGHT)
    end
    if updown==Input::DOWN
      return 1 if leftright==Input::LEFT
      return 3 if leftright==Input::RIGHT
      return 2
    elsif updown==Input::UP
      return 7 if leftright==Input::LEFT
      return 9 if leftright==Input::RIGHT
      return 8
    else
      return 4 if leftright==Input::LEFT
      return 6 if leftright==Input::RIGHT
      return 0
    end
  end

  def self.count(button)
    for btn in self.buttonToKey(button)
      c = self.repeatcount(btn)
      return c if c>0
    end
    return 0
  end

  def self.release?(button)
    rc = 0
    for btn in self.buttonToKey(button)
      c = self.repeatcount(btn)
      return false if c>0
      rc += 1 if self.releaseex?(btn)
    end
    return rc>0
  end

  def self.trigger?(button)
    return self.buttonToKey(button).any? {|item| self.triggerex?(item) }
  end

  def self.repeat?(button)
    return self.buttonToKey(button).any? {|item| self.repeatex?(item) }
  end

  def self.press?(button)
    return self.count(button)>0
  end

  def self.repeatex?(key)
    return false if !@keystate
    updateKeyState(key)
    return @keystate[key]==1 || (@keystate[key]>20 && (@keystate[key]&1)==0)
  end

  def self.releaseex?(key)
    return false if !@releasestate
    updateKeyState(key)
    return @releasestate[key]
  end

  def self.triggerex?(key)
    return false if !@triggerstate
    updateKeyState(key)
    return @triggerstate[key]
  end

  def self.repeatcount(key)
    return 0 if !@keystate
    updateKeyState(key)
    return @keystate[key]
  end

  def self.pressex?(key)
    return self.repeatcount(key)>0
  end
end



# Requires Win32API
module Mouse
  gsm             = Win32API.new('user32','GetSystemMetrics','i','i')
  @GetCursorPos   = Win32API.new('user32','GetCursorPos','p','i')
  @SetCapture     = Win32API.new('user32','SetCapture','p','i')
  @ReleaseCapture = Win32API.new('user32','ReleaseCapture','','i')
  module_function

  def getMouseGlobalPos
    pos = [0, 0].pack('ll')
    return (@GetCursorPos.call(pos)!=0) ? pos.unpack('ll') : nil
  end

  def screen_to_client(x, y)
    return nil unless x and y
    screenToClient = Win32API.new('user32','ScreenToClient',%w(l p),'i')
    pos = [x, y].pack('ll')
    return pos.unpack('ll') if screenToClient.call(Win32API.pbFindRgssWindow,pos)!=0
    return nil
  end

  def setCapture
    @SetCapture.call(Win32API.pbFindRgssWindow)
  end

  def releaseCapture
    @ReleaseCapture.call
  end

  # Returns the position of the mouse relative to the game window.
  def getMousePos(catch_anywhere=false)
    resizeFactor = ($ResizeFactor) ? $ResizeFactor : 1
    x, y = screen_to_client(*getMouseGlobalPos)
    width, height = Win32API.client_size
    if catch_anywhere or (x>=0 and y>=0 and x<width and y<height)
      return (x/resizeFactor).to_i, (y/resizeFactor).to_i
    end
    return nil
  end

  def del
    return if @oldcursor==nil
    @SetClassLong.call(Win32API.pbFindRgssWindow,-12,@oldcursor)
    @oldcursor = nil
  end
end