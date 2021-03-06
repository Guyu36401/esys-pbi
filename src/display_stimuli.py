import gc, random, sys
import pylsl

from pylsl import StreamInfo, StreamOutlet
from psychopy import prefs
prefs.general['audioLib'] = ['pygame']
from psychopy import visual, core, sound 
import win32api as win
import esys_cfg

stim = None

class Stimuli(object):
  LSL_STREAM_NAME = 'psychopy'
  LSL_STREAM_TYPE = 'marker'
  LSL_NUM_CHANNELS = 2
  LSL_SAMPLE_RATE = 0 # irregular sample rate. push whenever there is data.

  def __init__(self, cfg_filename):
    # load in the cfg
    self.cfg = esys_cfg.create_config(cfg_filename)

    # psychopy setup
    self.window = visual.Window(self.cfg.resolution)

    # preload all of stimuli, in sorted order
    self.loaded_stims = {}
    for trial_name, trial in self.cfg.trials.iteritems():
      stimuli_type = trial.stimuli_type
      path_prefix = '%s/' % trial.stimuli_folder

      if stimuli_type == 'images':
        self.loaded_stims[trial_name] = [ visual.ImageStim(self.window, 
                                            '%s%s' % (path_prefix, stim_file)) 
                                          for stim_file in trial.files[:-1]]
        self.fix_file = visual.ImageStim(self.window,'%s%s' %(path_prefix, trial.files[-1]))

      elif stimuli_type == 'sounds':
        self.loaded_stims[trial_name] = [ sound.Sound(
                                            '%s%s' % (path_prefix, stim_file))
                                          for stim_file in trial.files[:-1]]
        self.fix_file = sound.Sound('%s%s' % (path_prefix, trial.files[-1]))
      else:
        print('Unsupported stimuli_type: %s' % stimuli_type)
        raise ValueError 

    # setup LSL 
    # TODO generalize uid
    info = StreamInfo(self.LSL_STREAM_NAME, self.LSL_STREAM_TYPE,
        self.LSL_NUM_CHANNELS, self.LSL_SAMPLE_RATE, 'string', 'uid1')
    self.outlet = StreamOutlet(info)

  def signal(self, stim, msg):
    self.outlet.push_sample([str(stim), msg])

  def do_image_stimuli(self, stim, duration_ms):
    stim.draw(self.window)
    self.window.flip()
    core.wait(duration_ms / 1000.0)
    #self.window.flip()

  def do_sound_stimuli(self, stim, duration_ms):
    stim.play()
    core.wait(duration_ms / 1000.0)
    stim.stop()

  def trigger_stimuli(self, stim_type, stim, duration_ms):
    self.signal(stim, 'pre')

    if stim_type == 'images':
      self.do_image_stimuli(stim, duration_ms)
    elif stim_type == 'sounds':
      self.do_sound_stimuli(stim, duration_ms)

    # post signal
    self.signal(stim, 'post')

  def transition_time(self, transition_time_ms, variation_ms):
    random_wait = random.randint(-variation_ms, variation_ms)
    core.wait(transition_time_ms / 1000.0 + random_wait / 1000.0)

  def select_fixation(self, fixation_source):
    if fixation_source == 'default':
    # TODO add proper fixation stimuli
      self.fixation = visual.ShapeStim(self.window,
	    vertices=((0.5,0),(-0.5,0),(0,0),(0,0.5),(0,-0.5)),lineWidth=3, closeShape=False, lineColor="white",size=0.1)
    elif fixation_source == 'stim_folder':
      self.fixation = self.fix_file

  def run_fixation(self, stimuli_type, duration_time_ms, transition_time_ms, transition_time_variation_ms, fixation_type, fix_stim_interval):
    if fixation_type != 'none':  
      if fixation_type == 'margin':
	self.trigger_stimuli(stimuli_type, self.fixation,
	duration_time_ms)
	self.transition_time(transition_time_ms,
	transition_time_variation_ms)
      if self.count == fix_stim_interval:
        self.trigger_stimuli(stimuli_type, self.fixation,
        duration_time_ms)
        self.transition_time(transition_time_ms,
        transition_time_variation_ms)
        self.count = 0
    
  def display(self, event):
    # send many times to get a handshake
    self.signal('EXPERIMENT_BEGIN', 'EXPERIMENT_BEGIN')
    core.wait(0.5)
    self.signal('EXPERIMENT_BEGIN', 'EXPERIMENT_BEGIN')
    core.wait(0.5)
    self.signal('EXPERIMENT_BEGIN', 'EXPERIMENT_BEGIN')
    core.wait(0.5)
    self.signal('EXPERIMENT_BEGIN', 'EXPERIMENT_BEGIN')
    core.wait(0.5)

    self.count = 0

    for trial_name in self.cfg.trial_order:
      try: # termination handling for windows
        if event.is_set():
          return
      except:
        pass

      trial = self.cfg.trials[trial_name]
      self.select_fixation(trial.fixation_source)
      # display fixation at start of trial (if selected)
      self.run_fixation(trial.stimuli_type, trial.duration_time_ms, 
                         trial.transition_time_ms, trial.transition_time_variation_ms, trial.fixation_type, None)

      if trial.ordering == 'random':
        random.shuffle(self.loaded_stims[trial_name])

      core.wait(trial.lead_in_time_ms / 1000.0)
     
      for loaded_stim in self.loaded_stims[trial_name]:
        self.trigger_stimuli(trial.stimuli_type, loaded_stim, 
            trial.duration_time_ms)
        self.transition_time(trial.transition_time_ms,
                             trial.transition_time_variation_ms)
        if trial.fix_stim_interval > 0:
	  #keeps track of number of stimuli being displayed (for purpose of fixation)
	  self.count = self.count + 1
	  #display fixation at set intervals (if selected)
	  self.run_fixation(trial.stimuli_type, trial.duration_time_ms, 
	          trial.transition_time_ms, trial.transition_time_variation_ms, None, trial.fix_stim_interval)
      #display fixation at end of trial (if selected)  
      self.run_fixation(trial.stimuli_type, trial.duration_time_ms, 
                         trial.transition_time_ms, trial.transition_time_variation_ms, trial.fixation_type, None)
      core.wait(trial.lead_out_time_ms / 1000.0)

    self.signal('EXPERIMENT_END', 'EXPERIMENT_END')

  def __str__(self):
    return ('Pushing on channel %s for experiment %s.' 
            % (self.LSL_STREAM_NAME, self.cfg.name))

  def __del__(self):
    self.window.close()

def load(cfg_filename):
  global stim
  stim = Stimuli(cfg_filename)

def start(event):
  '''
  Precondition: load(cfg_file) must have been called prior to calling
                this function, to preload all stimuli.
  '''
  if stim is None:
    print('Call the load(cfg_filename) function first to initialize stim.')
    raise TypeError

  stim.display(event)

def stop():
  if stim is None:
    print("No window to close! The experiment hasn't even start()ed.")
    raise TypeError

  # dirty
  del(stim)
  gc.collect()

def win_handler(dwCtrlType):
  if dwCtrlType in (0,2,6):
    return 1
  #return 0

def main():
  # TODO generalize to command line args
  load('../stimulus-config/test.yml')

  start(None)

  if len(sys.argv) > 1:
    msg_queue = sys.argsv[1]
    msg_queue.put('FINISHED')

# to be called from multiprocessing
# event should be filled if on Windows, otherwise None
def begin(queue, event=None):
  # TODO generalize to command line args
  if sys.platform == 'win32':
    win.SetConsoleCtrlHandler(win_handler, 1)

  load('../stimulus-config/test.yml')
	   
  while True:
    msg = queue.get()
    if msg == 'BEGIN':
      break

  start(event)

  queue.put('FINISHED')

if __name__ == '__main__':
  main()
