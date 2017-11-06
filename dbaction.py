#!/usr/bin/env python
import getopt
import itertools
import os.path
import sys
import time
import setting
from dump import Dump
from dbsqlite import DbSqlite

class Dbaction(object):
	"""Do stuff with the fuzzer's databases: copy databases, print tables, insert stuff and generate testcases"""
	def __init__(self, settings):
		self.settings = settings
		if 'max_permutation' not in self.settings:
			self.settings['max_permutation'] = 5
		if 'generate_type' not in self.settings:
			self.settings['generate_type'] = 2

	def printtable(self, fromdb, table):
		"""Print all the conents of a table"""
		if table is None:
			print "You must select a table.\n"
			help()
		self.settings['output_file'] = None
		self.settings['db'] = DbSqlite(self.settings, fromdb)
		columns = self.settings['db'].get_columns(table)
		rows = self.settings['db'].get_rows(table)
		if columns:
			self.settings['output_width'] = 130
			dump = Dump(self.settings)
			dump.general("txt", table, columns, [rows])
		else:
			print "Error: table not found"

	def inserttable(self, fromdb, table, separator, insert):
		"""Insert a row into a table"""
		if table is None:
			print "You must select a table.\n"
			help()
		self.settings['db'] = DbSqlite(self.settings, fromdb)
		columns = self.settings['db'].get_columns(table)
		if columns:
			# If the user supplied one value less than the one required and the first column is called id, just ignore that column..
			if len(columns) == (len(insert.split(separator))+1) and columns[0] == 'id':
				del columns[0]
			if len(columns) != len(insert.split(separator)):
				print "The table '" + table + "' has " + str(len(columns)) + " columns: " + str(columns) + ". However, you want to insert " + str(len(insert.split(separator))) + " value/s: " + str(insert.split(separator)) + ". It doesn't work like that."
			else:
				self.settings['db'].insert_row(table, columns, insert.split(separator))
		else:
			print "Error: table not found"

	def permute(self, functions, values):
		"""Perform a permutation between the two lists received (functions & values)"""
		total = 0
		# Prioritize the lower count injections
		for count in range(0, self.settings['max_permutation']):
			# Give a heads up of how many testcases will be generated
			subtotal = 0
			countfunctions = functions
			for function in countfunctions:
				if isinstance(function, tuple):
					if len(function) == 1:
						function = function[0] # when it is generated by random testcases (fuzzer.py)
					elif len(function) == 2:
						function = function[1] # when it is read from the database
				if function is not None and count == function.count("[[test]]"):
					subtotal += 1
			self.settings['logger'].debug("Testcases generation: %s entry points, %s testcases to be generated." % (str(count), str(subtotal)))
			# Generate the testcases
			for function in functions:
				if len(function) == 1:
					function = function[0] # when it is generated by random testcases (fuzzer.py)
				elif len(function) == 2:
					function = function[1] # when it is read from the database
				if function is not None and count == function.count("[[test]]"):
					testcases, total = self.permuteValues(values, function, total)
					self.settings['db'].set_testcase(testcases)
		return total

	def permuteValues(self, values, function, total):
		"""Perform a permutation between the values and the functions received based on the generate_type received"""
		testcases = []
		function_tuple = function

		# There are no values, only functions:
		if len(values) == 0:
			testcases.append((unicode(function_tuple),))
		else:
			if self.settings['generate_type'] == 1:
				# Permute
				for valuetuple in itertools.product(values, repeat=function_tuple.count("[[test]]")):
					total += 1
					for value in valuetuple:
						# unicode values are tuples
						if isinstance(valuetuple, tuple):
							value = value[0]
						value = value.replace('[[id]]', str(total))
						function_tuple = function_tuple.replace("[[test]]", value, 1)
					#print "test:",function_tuple.encode("utf-8")[:self.settings['first']],":tset"
					testcases.append((unicode(function_tuple),))
					function_tuple = function # reset to the original value
			elif self.settings['generate_type'] == 2:
				# Do not permute, just replace
				for value in values:
					if isinstance(value, tuple):
						value = value[0]
					total += 1
					value = value.replace('[[id]]', str(total))
					function_tuple = function_tuple.replace('[[test]]', value)
					testcases.append((unicode(function_tuple),))
					function_tuple = function # reset to the original value
			elif self.settings['generate_type'] == 3:
				# Do not permute, replace but also include testcases with less parameters
				if (function.count("[[test]]")) > 1:
					for tests in range(1, function.count("[[test]]")+1):
						#print function_tuple
						for value in values:
							if isinstance(value, tuple):
								value = value[0]
							total += 1
							value = value.replace('[[id]]', str(total))
							function_tuple = function_tuple.replace('[[test]]', value)
							#print function_tuple
							testcases.append((unicode(function_tuple),))
							function_tuple = function # reset to the original value
						function_tuple = function = function.replace(',[[test]]', '', 1)
					#print testcases
			else:
				print "Error: the permutation type does not exist"
				sys.exit()

		return testcases, total

	def generate(self, fromdb):
		"""Generate the testcases with a permutation of values and functions"""
		startTime = time.time()
		self.settings['db'] = DbSqlite(self.settings, fromdb)

		self.settings['db'].create_table()
		values = self.settings['db'].get_values()
		functions = self.settings['db'].get_functions()
		self.settings['logger'].info("Values: %s - Functions: %s" % (str(len(values)), str(len(functions))))
		total = self.permute(functions, values)

		self.settings['db'].commit()
		finishTime = time.time() - startTime
		self.settings['logger'].info("Testcases generated: %s" % str(total))
		self.settings['logger'].info("Time required: %s seconds" % str(round(finishTime, 2)))

	def migrate(self, fromdb, todb):
		"""Migrates tables from one database ('dbfrom') to another database ('dbto')"""
		startTime = time.time()
		self.settings['dbfrom'] = DbSqlite(self.settings, fromdb)
		self.settings['dbto'] = DbSqlite(self.settings, todb)

		self.settings['dbto'].create_table()

		values = self.settings['dbfrom'].get_values()
		self.settings['dbto'].set_values(values)

		functions = self.settings['dbfrom'].get_functions()
		self.settings['dbto'].set_functions(functions)

		self.settings['dbto'].commit()

		finishTime = time.time() - startTime
		self.settings['logger'].info("Finished, time elapsed %s seconds" % str(finishTime)[:5])

def help(err=None):
	"""Print a help screen and exit"""
	if err:
		print("Error: " + str(err))
	print "Syntax: "
	print os.path.basename(__file__) + "  -d db.sqlite -D fuzz.db             Migrate database information"
	print                         "\t     -d fuzz.db -g 1 [-m 5]              Generate testcases permuting values and functions (set to maximum 5 input test cases)"
	print                         "\t     -d fuzz.db -g 2 [-m 5]              Generate testcases replacing values in functions (set to max..)"
	print                         "\t     -d fuzz.db -g 3 [-m 5]              Generate testcases replacing values in functions including testcases with less parameters (set to max..)"
	print                         "\t     -d fuzz.db -t table -p              Print a database table: fuzz_software, fuzz_testcase, value, function)"
	print                         "\t     -d fuzz.db -t table [-s,] -i \"foo\"  Insert foo into table (optional field separator -s uses a comma)"
	sys.exit()

def main():
	"""Perform multiple database actions"""
	try:
		opts, args = getopt.getopt(sys.argv[1:], "hd:D:g:i:m:ps:t:", ["help", "database=", "Database=", "generate=", "insert=", "maximum=", "print", "separator=", "table="])
	except getopt.GetoptError as err:
		print str(err),"\n" # will print something like "option -a not recognized"
		help()

	settings = {}
	fromdb = None
	todb = None
	table = None
	action = None
	separator = ","

	for o, a in opts:
		if o in ("-h", "--help"):
			help()
		elif o in ("-d", "--database"):
			fromdb = a
			if os.path.isfile(fromdb):
				settings['db_file'] = fromdb
			else:
				print "Error: The database selected '" + a + "' is not a valid file:"
		elif o in ("-D", "--Database"):
			todb = a
			action = "migrate"
			break
		elif o in ("-g", "--generate"):
			action = "generate"
			settings['generate_type'] = int(a)
		elif o in ("-i", "--insert"):
			action = "insert"
			insert = unicode(str(a), errors='ignore')
		elif o in ("-m", "--maximum"):
			settings['max_permutation'] = int(a)
		elif o in ("-p", "--print"):
			action = "print"
		elif o in ("-s", "--separator"):
			separator = a
		elif o in ("-t", "--table"):
			table = a

	if not fromdb:
		help("The database was not specified.")
		
	settings = setting.load_settings(settings)
	dbaction = Dbaction(settings)
	if action == "migrate":
		dbaction.migrate(fromdb, todb)
	elif action == "generate":
		if todb is not None:
			fromdb = todb
		dbaction.generate(fromdb)
	elif action == "print":
		dbaction.printtable(fromdb, table)
	elif action == "insert":
		dbaction.inserttable(fromdb, table, separator, insert)
	else:
		print "Error: You must select an action: migrate, generate, print or insert."
		help()

if __name__ == "__main__":
	main()
