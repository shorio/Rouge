import libtcodpy as libtcod
import math
import textwrap
import shelve

#Console Variables
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50
LIMIT_FPS = 30

#Map variables
MAP_WIDTH = 80
MAP_HEIGHT = 43

#Dungeon Generation
ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30

#fog
FOV_ALGO = 0
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10

#stats
LEVEL_UP_BASE = 200
LEVEL_UP_FACTOR = 150

HEAL_AMOUNT = 4
LIGHTNING_DAMAGE = 20
LIGHTNING_RANGE = 5
CONFUSED_NUM_TURNS = 10
CONFUSE_RANGE = 8
FIREBALL_RADIUS = 3
FIREBALL_DAMAGE = 12

#colors
color_dark_wall = libtcod.Color(0, 0, 100)
color_light_wall = libtcod.Color(130, 110, 50)
color_dark_ground = libtcod.Color(50, 50, 150)
color_light_ground = libtcod.Color(200, 180, 50)

#gui
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT
MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1
INVENTORY_WIDTH = 50
LEVEL_SCREEN_WIDTH = 40
CHARACTER_SCREEN_WIDTH = 30

class Tile:
	"""
	a tile of the map and its properties
	"""
	def __init__(self, blocked, block_sight = None):
		self.explored = False
		self.blocked = blocked
		
		#By default, if a tile is blocked, it also blocks sight
		if block_sight is None:
			block_sight = blocked 
		self.block_sight = block_sight
		
class Rect:
	"""
	a rectangle on the map, used to characterize a room
	"""
	def __init__(self, x, y, w, h):
		self.x1 = x
		self.y1 = y
		self.x2 = x + w
		self.y2 = y + h
		
	def center(self):
		center_x = (self.x1 + self.x2) / 2
		center_y = (self.y1 + self.y2) / 2
		return (center_x, center_y)
	
	def intersect(self, other):
		#returns true if this rectangle intersects with another one
		return (self.x1 <= other.x2 and self.x2 >= other.x1 and self.y1 <= other.y2 and self.y2 >= other.y1)

class Object:
	"""
	This is a generic object: the player, a monster, an item, the stairs . . .
	It's always represented by a character on the screen
	"""
	def __init__(self, x, y, char, name, color, blocks = False, always_visible = False, fighter = None, ai = None, item = None):
		self.x = x
		self.y = y
		self.char = char
		self.name = name
		self.color = color
		self.blocks = blocks
		self.always_visible = always_visible
		self.fighter = fighter
		if self.fighter: #let the fighter component know who owns it
			self.fighter.owner = self
			
		self.ai = ai
		if self.ai: #let the AI component know who owns it
			self.ai.owner = self
			
		self.item = item
		if self.item: #let the Item component know who owns it
			self.item.owner = self
		
	def move(self, dx, dy):
		#move by the given amount
		if not is_blocked(self.x + dx, self.y + dy):
			self.x += dx
			self.y += dy
	
	def move_towards(self, target_x, target_y):
		#vector from this object to the target, and distance
		dx = target_x - self.x
		dy = target_y - self.y
		distance = math.sqrt(dx ** 2 + dy ** 2)
		
		#normalize it to length 1 (preserving direction), the round it and
		#convert to integer so the movement is restricted to the map grid
		dx = int(round(dx / distance))
		dy = int(round(dy / distance))
		self.move(dx, dy)
		
	def distance_to(self, other):
		#return the distance to another object
		dx = other.x - self.x
		dy = other.y - self.y
		return math.sqrt(dx ** 2 + dy ** 2)
		
	def distance(self, x, y):
		#return this distance to some coordinates
		return math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)
	
	def draw(self):
		#set the color and then draw the character that represents this object at its position
		if libtcod.map_is_in_fov(fov_map, self.x, self.y) or (self.always_visible and map[self.x][self.y].explored):
			libtcod.console_set_default_foreground(con, self.color)
			libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)
		
	def clear(self):
		#erase the character that represents this object
		libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)
	def send_to_back(self):
		#make this object be drawn first, so all others appear above it if they're in the same tile.
		global objects
		objects.remove(self)
		objects.insert(0, self)

class Fighter:
	"""
	combat-related properties and methods (monster, player, NPC)
	"""
	def __init__(self, hp, defense, power, xp, death_function = None, boss = False):
		self.max_hp = hp
		self.hp = hp
		self.defense = defense
		self.power = power
		self.xp = xp
		self.death_function = death_function
		self.boss = boss
	
	def take_damage(self, damage):
		#apply damage if possible
		if damage > 0:
			self.hp -= damage
		if self.hp <= 0:
			function = self.death_function
			if function is not None:
				function(self.owner)
			if self.owner != player: #yield xp
				player.fighter.xp += self.xp
			
	def attack(self, target):
		#a simple formula for attack damage
		damage = self.power - target.fighter.defense
		
		if damage > 0:
			#make the target take some damage
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.')
			target.fighter.take_damage(damage)
		else:
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect!')
			
	def heal(self, amount):
		#heal by the given amount, without going over the maximum
		self.hp += amount
		if self.hp > self.max_hp:
			self.hp = self.max_hp

class BasicMonster:
	#AI for a basic monster
	def take_turn(self):
		#a basic monster takes its turn. If you can see it, it can see you
		monster = self.owner
		if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
			#move towards player if far away
			if monster.distance_to(player) >= 2:
				monster.move_towards(player.x, player.y)
				
			#close enough, attack! (if the player is still alive.)
			elif player.fighter.hp > 0:
				monster.fighter.attack(player)

class ConfusedMonster:
	#AI for a confused monster
	def __init__(self, old_ai, num_turns = CONFUSED_NUM_TURNS):
		self.old_ai = old_ai
		self.num_turns = num_turns
	
	def take_turn(self):
		if self.num_turns ==  0:
			#move in a random direction
			self.owner.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))
			self.num_turns -= 1
		
		else: #restore
			self.owner.ai = self.old_ai
			message('The ' + self.owner.name + ' is no longer confused!', libtcod.red)
				
class Item:
	#an item that can be picked up and used
	
	def __init__(self, use_function = None):
		self.use_function = use_function
	
	def pick_up(self):
		#add to the player's inventory and remove from the map
		if len(inventory) >= 26:
			message('Your inventory is full, cannot pick up ' + self.owner.name + '.', libtcod.red)
		else:
			inventory.append(self.owner)
			objects.remove(self.owner)
			message('You picked up a ' + self.owner.name + '!', libtcod.green)
			
	def use(self):
		#just call the "use_function" if it is defined
		if self.use_function is None:
			message('The ' + self.owner.name + ' cannot be used.')
		else:
			if self.use_function() != 'cancelled':
				inventory.remove(self.owner) #destroy after use, unless it was cancelled
				
	def drop(self):
		#add to the map and remove from the player's inventory and place at player's coordinates
		objects.append(self.owner)
		inventory.remove(self.owner)
		self.owner.x = player.x
		self.owner.y = player.y
		message('You dropped a ' + self.owner.name + '.', libtcod.yellow)
	
def create_room(room):
	global map
	#go through the tiles in the rectangle and make them passable
	for x in range(room.x1 + 1, room.x2):
		for y in range(room.y1 + 1, room.y2):
			map[x][y].blocked = False
			map[x][y].block_sight = False

def create_h_tunnel(x1, x2, y):
	global map
	#horizontal tunnel
	for x in range(min(x1, x2), max(x1, x2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False
		
def create_v_tunnel(y1, y2, x):
	global map
	#vertical tunnel
	for y in range(min(y1, y2), max(y1, y2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False
		
def make_map():
	global map, objects, stairs, boss
	
	#list of objects with just player
	objects = [player, ]
	#fill map with walls
	map = [[ Tile(True) for y in range(MAP_HEIGHT) ] for x in range(MAP_WIDTH) ]

	rooms = []
	num_rooms = 0
	
	#boss time
	if dungeon_level % 10 == 0:
		boss = True
		first_room = Rect(1, 1, MAP_WIDTH / 5, MAP_HEIGHT - 2)
		second_room = Rect(MAP_WIDTH / 2, 1, MAP_WIDTH / 2 - 1, MAP_HEIGHT - 2)
		create_room(first_room)
		create_room(second_room)
		rooms.append(first_room)
		rooms.append(second_room)
		player.x, player.y = first_room.center()
		new_x, new_y = second_room.center()
		create_h_tunnel(player.x, new_x, player.y)
		place_objects(second_room)
		num_rooms = 2
	
	else:
		for r in range(MAX_ROOMS):
			#random width and height
			w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
			h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
			
			#random position without going out of the boundaries of the map
			x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
			y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
			
			new_room = Rect(x, y, w, h)
			
			#run through the other rooms and see if they intersect with this one
			failed = False
			for other_room in rooms:
				if new_room.intersect(other_room):
					failed = True
					break
			
			if not failed:
				#this means there are no intersections, so this room is valid
				
				#"paint" it to the map's tiles
				create_room(new_room)
				
				#center coordinates of new room
				new_x, new_y = new_room.center()
				
				if num_rooms == 0:
					#this is the first room, where the player starts at
					player.x = new_x
					player.y = new_y
				else:
					#all rooms after the first
					#connect it to the previous room with a tunnel
					
					#center coordinates of previous room
					prev_x, prev_y = rooms[num_rooms - 1].center()
					
					#random number that is either 0 or 1
					if libtcod.random_get_int(0, 0, 1) == 1:
						#first move horizontally, then vertically
						create_h_tunnel(prev_x, new_x, prev_y)
						create_v_tunnel(prev_y, new_y, new_x)
					else:
						#first move vertically, then horizontally
						create_v_tunnel(prev_y, new_y, prev_x)
						create_h_tunnel(prev_x, new_x, new_y)
						
				#finally, append the new room to the list
				rooms.append(new_room)
				
				#populate
				place_objects(new_room)
				num_rooms += 1
		#boss/miniboss handling
		boss = False
		if dungeon_level % 5 == 0 and dungeon_level % 10 != 0:
			boss = True
			#create miniboss
			fighter_component = Fighter(hp = 25, defense = 2, power = 6, xp = 200, death_function = monster_death, boss = boss)
			ai_component = BasicMonster()
			monster = Object(new_x, new_y, 'm', 'miniboss', libtcod.red, blocks = True, fighter = fighter_component, ai = ai_component)
			objects.append(monster)
		elif dungeon_level % 10 == 0:
			boss = True
			#create da boss
		#create stairs at the center of the last room
	stairs = Object(new_x, new_y, '<', 'stairs', libtcod.white, always_visible = True)
	objects.append(stairs)

def place_objects(room):
	if dungeon_level % 10 == 0:
		#create boss
		cx, cy = room.center()
		fighter_component = Fighter(hp = 100, defense = 5, power = 8, xp = 300, death_function = monster_death, boss = boss)
		ai_component = BasicMonster()
		monster = Object(cx, cy, 'B', 'boss', libtcod.dark_red, blocks = True, fighter = fighter_component, ai = ai_component)
		objects.append(monster)
	#choose random number of monsters
	max_monsters = int(math.floor(math.sqrt(dungeon_level)))
	num_monsters = libtcod.random_get_int(0, 0, max_monsters)
	
	for i in range(num_monsters):
		#choose random spot for this monster
		x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
		y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)
		
		if not is_blocked(x, y):
			dice = libtcod.random_get_int(0, 0, 100)
			if  dice < 80: #80% chance of getting an orc
				#create orc
				fighter_component = Fighter(hp = 10, defense = 0, power = 3, xp = 35, death_function = monster_death)
				ai_component = BasicMonster()
				monster = Object(x, y, 'o', 'orc', libtcod.desaturated_green, blocks = True, fighter = fighter_component, ai = ai_component)
			else:
				#create a troll
				fighter_component = Fighter(hp = 16, defense = 1, power = 4, xp = 100, death_function = monster_death)
				ai_component = BasicMonster()
				monster = Object(x, y, 'T', 'troll', libtcod.darker_green, blocks = True, fighter = fighter_component, ai = ai_component)
				
			objects.append(monster)
			
	#choose random number of items
	max_items = int(math.floor(math.sqrt(math.sqrt(dungeon_level))))
	num_items = libtcod.random_get_int(0, 0, max_items)
	
	for i in range(num_items):
		#choose random spot for this item
		x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
		y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)
		
		#only place it if the tile is not blocked
		if not is_blocked(x, y):
			dice = libtcod.random_get_int(0, 0, 100)
			if dice < 70:
				#create a healing potion
				item_component = Item(use_function = cast_heal)
				item = Object(x, y, '!', 'healing potion', libtcod.violet, item = item_component)
			elif dice < 80:
				#create a  lightning bolt scroll
				item_component = Item(use_function = cast_lightning)
				item = Object(x, y, '#', 'scroll of lightning bolt', libtcod.light_yellow, item = item_component)
			elif dice < 90:
				#create a fireball scroll
				item_component = Item(use_function = cast_fireball)
				item = Object(x, y, '#', 'scroll of fireball', libtcod.light_yellow, item = item_component)
			else:
				#create a confused scroll
				item_component = Item(use_function = cast_confuse)
				item = Object(x, y, '#', 'scroll of confusion', libtcod.light_yellow, item = item_component)
			objects.append(item)
			item.send_to_back()
	
def render_all():
	global fov_map
	global color_dark_wall, color_light_wall
	global color_dark_ground, color_light_ground
	global fov_recompute
	
	if fov_recompute:
		#recompute FOV if needed (the player moved or something)
		fov_recompute = False
		libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)
	
		#create all tiles
		for y in range(MAP_HEIGHT):
			for x in range(MAP_WIDTH):
				visible = libtcod.map_is_in_fov(fov_map, x, y)
				wall = map[x][y].block_sight
				if not visible:
					#if it's not visible right now, the player can only see it if it's explored
					if map[x][y].explored:
						#out of player's POV
						if wall:
							libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET)
						else:
							libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET)
				else:
					#it's visible
					if wall:
						libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET)
					else:
						libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET)
					#since it's visible, mark as explored
					map[x][y].explored = True
	
	#draw all objects in the list; draw player last
	for object in objects:
		if object != player:
			object.draw()
	player.draw()
				
	#draw from remote to root
	libtcod.console_blit(con, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0, 0)
	
	#gui
	libtcod.console_set_default_background(panel, libtcod.black)
	libtcod.console_clear(panel)
	
	#print the game messages, one line at a time
	y = 1
	for (line, color) in game_msgs:
		libtcod.console_set_default_foreground(panel, color)
		libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
		y += 1
	
	#show player's stats
	render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp, libtcod.light_red, libtcod.darker_red)
	
	#display names of objects under the mouse
	libtcod.console_set_default_foreground(panel, libtcod.light_gray)
	libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())
	
	#blit the contents of "panel" to the root console
	libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)
			
def is_blocked(x, y):
	#first test the map tile
	if map[x][y].blocked:
		return True
		
	#now check for any blocking objects
	for object in objects:
		if object.blocks and object.x == x and object.y == y:
			return True
			
	return False

def player_move_or_attack(dx, dy):
	global fov_recompute
	
	#the coordinates the player is moving to/attacking
	x = player.x + dx
	y = player.y + dy
	
	#try to find an attackable object there
	target = None
	for object in objects:
		if object.fighter and object.x == x and object.y == y:
			target = object
			break
	
	#attack if target found, move otherwise
	if target is not None:
		player.fighter.attack(target)
	else:
		player.move(dx, dy)
		fov_recompute = True
		
def check_level_up():
	#see if player levels up
	level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
	if player.fighter.xp >= level_up_xp:
		#yay
		player.level += 1
		player.fighter.xp -= level_up_xp
		message('Your battle skills grow stronger! You reached level ' + str(player.level) + '!', libtcod.yellow)
		choice = None
		while choice == None:
			choice = menu('Level up! Choose a stat to raise:\n',
				['Constitution (+20 HP, from ' + str(player.fighter.max_hp) + ')',
				'Strength (+1 attack, from ' + str(player.fighter.power) + ')',
				'Agility (+1 defense, from ' + str(player.fighter.defense) + ')'], LEVEL_SCREEN_WIDTH)
		
		if choice == 0:
			player.fighter.max_hp += 20
			player.fighter.hp += 20
		elif choice == 1:
			player.fighter.power += 1
		elif choice == 2:
			player.fighter.defense += 1

def get_names_under_mouse():
	global mouse
	
	#return a string with the names of all objects under the mouse
	(x, y) = (mouse.cx, mouse.cy)
	
	#create a list with the names of all objects at the mouse's coordinates and in FOV
	names = [obj.name for obj in objects if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
	names = ', '.join(names) #joins the name, separated by commas
	return names.capitalize()
	
def target_tile(max_range = None):
	#return position of tile left-clicked in player's FOV or (None, None) if right-clicked
	global key, mouse
	while True:
		#render the screen. This erase the inventory and shows the name of objects under the mouse
		libtcod.console_flush()
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE, key, mouse)
		render_all()
		
		x, y = mouse.cx, mouse.cy
		
		if mouse.lbutton_pressed and libtcod.map_is_in_fov(fov_map, x, y) and (max_range is None or player.distance(x, y) <= max_range):
			return (x, y)
		if mouse.rbutton_pressed or key.vk == libtcod.KEY_ESCAPE:
			return (None, None) #cancel
			
def target_monster(max_range = None):
	#returns a clicked monster inside FOV up to a range, or None if right-clicked
	while True:
		x, y = target_tile(max_range)
		if x is None: #cancelled
			return None
		
		#return first clicked monster, otherwise continue
		for obj in objects:
			if obj.x == x and obj.y == y and obj.fighter and obj != player:
				return obj
	
def menu(header, options, width):
	if len(options) > 26:
		raise ValueError('Cannot have a menu with more than 26 options.')
	#calculate total height for the header (after auto-wrape) and one line per option
	if header == '':
		header_height = 0
	else:
		header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
	height = len(options) + header_height
	
	#create off-screen console that represents the menu's window
	window = libtcod.console_new(width, height)
	
	#print the header, with auto-wrap
	libtcod.console_set_default_foreground(window, libtcod.white)
	libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)
	
	#print all the options
	y = header_height
	letter_index = ord('a')
	for option_text in options:
		text = '(' + chr(letter_index) + ') ' + option_text
		libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
		y += 1
		letter_index += 1
		
	#blit the contents of "window" to the root console
	x = SCREEN_WIDTH / 2 - width / 2
	y = SCREEN_HEIGHT / 2 - height / 2
	libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)
	
	#present the root console to the player and wait for a key-press
	libtcod.console_flush()
	key = libtcod.console_wait_for_keypress(True)
	
	if key.vk == libtcod.KEY_ENTER and key.lalt:  #(special case) Alt+Enter: toggle fullscreen
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
	
	#convert the ASCII code to an index; if it corresponds to an option, return it
	index = key.c - ord('a')
	if index >= 0 and index < len(options):
		return index
	return None
	
def inventory_menu(header):
	#show a menu with each item of the inventory as an option
	if len(inventory) == 0:
		options = ['Inventory is empty.']
	else:
		options = [item.name for item in inventory]
	
	index = menu(header, options, INVENTORY_WIDTH)
	
	#if an item was chosen, return it
	if index is None or len(inventory) == 0:
		return None
	return inventory[index].item
		
def handle_keys():
	global key;
	#key = libtcod.console_wait_for_keypress(True)
	if key.vk == libtcod.KEY_ENTER and key.lalt:
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
	elif key.vk == libtcod.KEY_ESCAPE:
		return 'exit' #exit game
	
	if game_state == 'playing':
		#arrow keys
		if key.vk == libtcod.KEY_UP:
			player_move_or_attack(0, -1)
		elif key.vk == libtcod.KEY_DOWN:
			player_move_or_attack(0, 1)
		elif key.vk == libtcod.KEY_LEFT:
			player_move_or_attack(-1, 0)
		elif key.vk == libtcod.KEY_RIGHT:
			player_move_or_attack(1, 0)
		else:
			#test for other keys
			key_char = chr(key.c)
			if key_char == 'g':
				#pick up an item
				for object in objects: #look for an item in the player's tile
					if object.x == player.x and object.y == player.y and object.item:
						object.item.pick_up()
						break
			if key_char == 'i':
				#show the inventory; if an item is selected, use it
				chosen_item = inventory_menu('Press the key next to an item to use it, or any other to cancel.\n')
				if chosen_item is not None:
					chosen_item.use()
			if key_char == 'd':
				#show the inventory; if an item is selected, drop it
				chosen_item = inventory_menu('Press the key next to an item to drop it, or any other to cancel.\n')
				if chosen_item is not None:
					chosen_item.drop()
			if key_char == ',':
				#go down stairs, if the player is on them
				if stairs.x == player.x and stairs.y == player.y:
					if not boss:
						next_level()
			if key_char == 'c':
				#show character information
				level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
				msgbox('Character Information\n\nLevel: ' + str(player.level) + '\nExperience: ' + str(player.fighter.xp) +
					'\nExperience to level up: ' + str(level_up_xp) + '\n\nMaximum HP: ' + str(player.fighter.max_hp) +
					'\nAttack: ' + str(player.fighter.power) + '\nDefense: ' + str(player.fighter.defense), CHARACTER_SCREEN_WIDTH)
			return 'didnt-take-turn'

def next_level():
	#advance to the next level
	global dungeon_level
	message('You take a moment to rest, and recover your strength.', libtcod.light_violet)
	player.fighter.heal(player.fighter.max_hp / 2) #heal the player by 50%
	
	message('After a rare moment of peace, you descend deeper into the lair of cute puppies and kitties', libtcod.red)
	dungeon_level += 1
	message('Level ' + str(dungeon_level) + '!', libtcod.light_violet)
	if dungeon_level % 5 == 0 and dungeon_level % 10 != 0:
		message('A chill runs down your spine', libtcod.dark_red)
	elif dungeon_level % 10 == 0:
		message('Oh no a boss :(', libtcod.dark_red)
	make_map() #create new level
	initialize_fov()
			
def cast_heal():
	#heal the player
	if player.fighter.hp == player.fighter.max_hp:
		message('You are already at full health.', libtcod.red)
		return 'cancelled'
	
	message('Your wounds start to feel better!', libtcod.light_violet)
	player.fighter.heal(HEAL_AMOUNT)
	
def cast_lightning():
	#find closest enemy (inside a maximum range) and damage it
	monster = closest_monster(LIGHTNING_RANGE)
	if monster is None: #no enemy found within maximum range
		message('No enemy is close enough to strike.', libtcod.red)
		return 'cancelled'
	
	#zap
	message('A lightning bolt strikes the ' + monster.name + ' with a loud thunder! The damage is ' + str(LIGHTNING_DAMAGE) + ' hit points.', libtcod.light_blue)
	monster.fighter.take_damage(LIGHTNING_DAMAGE)
	
def cast_confuse():
	#find closest enemy in-range and confuse it
	message('Left-click an enemy to confuse it, or right click to cancel', libtcod.light_cyan)
	monster = target_monster(CONFUSE_RANGE)
	if monster is None:
		return 'cancelled'
	#replace the monster's AI with a "confused" one; after some turns restore old AI
	old_ai = monster.ai
	monster.ai = ConfusedMonster(old_ai)
	monster.ai.owner = monster #tell the new component who owns it
	message('The eys of the ' + monster.name + ' look vacant, as he starts to stumble around!', libtcod.light_green)

def cast_fireball():
	#ask the player for a target tile to throw a fireball at
	message('Left-click a target tile for the fireball, or right-click to cancel.', libtcod.light_cyan)
	x, y = target_tile()
	if x is None:
		return 'cancelled'
	message('The fireball explodes, burning everything within ' + str(FIREBALL_RADIUS) + ' tiles!', libtcod.orange)
	
	for obj in objects: #damage every fighter in range, including player
		if obj.distance(x, y) <= FIREBALL_RADIUS and obj.fighter:
			message('The ' + obj.name + ' gets burned for ' + str(FIREBALL_DAMAGE) + ' hit points.', libtcod.orange)
			obj.fighter.take_damage(FIREBALL_DAMAGE)
	
def closest_monster(max_range):
	#find closest enemy, up to a maximum range, and in the player's FOV
	closest_enemy = None
	closest_dist = max_range + 1 #start with (slightly more than) maximum range
	
	for object in objects:
		if object.fighter and not object == player and libtcod.map_is_in_fov(fov_map, object.x, object.y):
			#calculate distance between this object and the player
			dist = player.distance_to(object)
			if dist < closest_dist: #it's closer, so remember it
				closest_enemy = object
				closest_dist = dist
	return closest_enemy

def player_death(player):
	#game over :(
	global game_state
	message('You died!', libtcod.red)
	game_state = 'dead'
	
	#corpse
	player.char = '%'
	player.color = libtcod.dark_red
	
def monster_death(monster):
	global boss
	#becomes corpse. it doesn't block, can't be attacked and doesn't move
	message(monster.name.capitalize()  + ' is dead! You gain ' + str(monster.fighter.xp) + ' experience points.', libtcod.orange)
	monster.char = '%'
	monster.color = libtcod.dark_red
	if monster.fighter.boss:
		boss = False
	monster.blocks = False
	monster.fighter = None
	monster.ai = None
	monster.name = 'remains of ' + monster.name
	monster.send_to_back()
	
def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
	#render a bar (HP, experience, etc). first calculate the width of the bar
	bar_width = int(float(value) / maximum * total_width)
	
	#render the background first
	libtcod.console_set_default_background(panel, back_color)
	libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)
	
	#now render the bar on top
	libtcod.console_set_default_background(panel, bar_color)
	if bar_width > 0:
		libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)
		
	#finally, some centered text with the values
	libtcod.console_set_default_foreground(panel, libtcod.white)
	libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER, name + ': ' + str(value) + '/' + str(maximum))

def message(new_msg, color = libtcod.white):
	#split the message if necessary, among multiple lines
	new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)
	
	for line in new_msg_lines:
		#if the buffer is full, remove the first line to make room for the new one
		if len(game_msgs) == MSG_HEIGHT:
			del game_msgs[0]
		
		#add the new line as a tuple, with the text and the color
		game_msgs.append((line, color))
		
def msgbox(text, width = 50):
	menu(text, [], width) #use menu() as a sort of message box

def main_menu():
	while not libtcod.console_is_window_closed():
		#show options and wait for the player's choice
		libtcod.console_print_ex(None, SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 - 4, libtcod.BKGND_NONE, libtcod.CENTER, 'Best Game')
		choice = menu('', ['Play a new game', 'Continue last game', 'Quit'], 24)
		
		if choice == 0: #new game
			new_game()
			play_game()
		elif choice == 1: #load last game
			try:
				load_game()
			except:
				msgbox('\n No savedgame to load.\n', 24)
				continue
			play_game()
		elif choice == 2: #quit
			break
		
def new_game():
	global player, inventory, game_msgs, game_state, dungeon_level
	
	#characters
	#create object representing the player
	fighter_component = Fighter(hp = 300, defense = 2, power = 20, xp = 0, death_function = player_death)
	player = Object(0, 0, '@', 'player', libtcod.white, blocks = True, fighter = fighter_component)
	
	player.level = 1
	
	dungeon_level = 1
	
	#create map
	make_map()
	initialize_fov()
	
	game_state = 'playing'
	
	inventory = []
	
	#create the list of game messages and their colors, starts empty
	game_msgs = []		

	#a warm welcoming message!
	message('Welcome stranger! Prepare to perish in this game!', libtcod.red)
	
def initialize_fov():
	global fov_recompute, fov_map
	fov_recompute = True
	#fov
	libtcod.console_clear(con) #unexplored areas start black
	fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)
			
def play_game():
	player_action = None
	#game loop
	while not libtcod.console_is_window_closed():
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE, key, mouse)
		render_all()
		
		#print remote on root
		libtcod.console_flush()
		check_level_up()
		
		#refresh
		for object in objects:
			object.clear()
		#handle keys
		player_action = handle_keys()
		if player_action == 'exit':
			save_game()
			break
			
		if game_state == 'playing' and player_action != 'didnt-take-turn':
			for object in objects:
				if object.ai:
					object.ai.take_turn()
					
def save_game():
	#open a new empty shelve (possibly overwriting an old one) to write game data
	file = shelve.open('savegame', 'n')
	file['map'] = map
	file['objects'] = objects
	file['player_index'] = objects.index(player)
	file['inventory'] = inventory
	file['game_msgs'] = game_msgs
	file['game_state'] = game_state
	file['stairs_index'] = objects.index(stairs)
	file['dungeon_level'] = dungeon_level
	file['boss'] = boss
	file.close()
	
def load_game():
	#open the previously saved shelve and load the game data
	global map, objects, player, inventory, game_msgs, game_state, stairs, dungeon_level
	
	file = shelve.open('savegame', 'r')
	map = file['map']
	objects = file['objects']
	player = objects[file['player_index']]
	inventory = file['inventory']
	game_msgs = file['game_msgs']
	game_state = file['game_state']
	stairs = objects[file['stairs_index']]
	dungeon_level = file['dungeon_level']
	boss = file['boss']
	print game_state
	file.close()
	
	initialize_fov()

#init root
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'Game', False)
#init offscreen
con = libtcod.console_new(SCREEN_WIDTH, SCREEN_HEIGHT)

libtcod.sys_set_fps(LIMIT_FPS)

#gui
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)

#mouse!
mouse = libtcod.Mouse()
key = libtcod.Key()

main_menu()