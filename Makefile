
minimal:core_tools

core_tools:
	rosmake --rosdep-install --bootstrap --status-rate=0
	@echo "You have built the minimal set of ROS tools."
	@echo "If you want to make all ROS tools type 'rosmake ros'."
	@echo "Or you can rosmake any other package in your ROS_PACKAGE_PATH."

clean:
	@if test -z `which rospack`; then echo "It appears that you have already done a 'make clean' because rospack is gone."; false; fi
	rosmake -r --target=clean ros

## include $(shell rospack find mk)/cmake_stack.mk
### copied below since it can't be found before rospack is built 

# set EXTRA_CMAKE_FLAGS in the including Makefile in order to add tweaks
#CMAKE_FLAGS= -Wdev -DCMAKE_TOOLCHAIN_FILE=`rospack find rosbuild`/rostoolchain.cmake $(EXTRA_CMAKE_FLAGS)
CMAKE_FLAGS= -Wdev -DCMAKE_TOOLCHAIN_FILE=../core/rosbuild/rostoolchain.cmake $(EXTRA_CMAKE_FLAGS)

# The all target does the heavy lifting, creating the build directory and
# invoking CMake
all_dist: minimal
	@mkdir -p build
	-mkdir -p bin
	cd build && cmake $(CMAKE_FLAGS) ..

# The clean target blows everything away
# It also removes auto-generated message/service code directories, 
# to handle the case where the original .msg/.srv file has been removed,
# and thus CMake no longer knows about it.
clean_dist:
	-cd build && make clean
	rm -rf build

# Run the script that does the build, then do a fairly hacky cleanup, #1598
package_source:
	$(shell rospack find rosbuild)/bin/package_source.py $(CURDIR)


