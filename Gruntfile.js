module.exports = function (grunt) {
    grunt.initConfig({
        pkg: grunt.file.readJSON('package.json'),
        bower_concat: {
            all: {
                dest: 'uber/static/deps/combined.js',
                cssDest: 'uber/static/deps/combined.css',
                callback: function (mainFiles, component) {
                    if (component === 'select2') {
                        // the default select2 file doesn't contain full functionality and we want the full thing
                        return mainFiles.map(function(filepath) {
                            return filepath.replace('select2.js', 'select2.full.js');
                        });
                    } else if (component === 'bootstrap') {
                        return mainFiles.concat([
                            process.cwd() + '/bower_components/bootstrap/dist/css/bootstrap-theme.css',
                            process.cwd() + '/bower_components/bootstrap/js/button.js'
                        ]);
                    } else if (component === 'jquery-ui') {
                        // jquery.select-to-autocomplete.js doesn't have a bower.json so we manually add it
                        // There's already a pull request to add bower support:
                        // https://github.com/JamieAppleseed/selectToAutocomplete/pull/93
                        return mainFiles.concat([
                            process.cwd() + '/bower_components/jquery-ui/themes/ui-lightness/jquery-ui.css',
                            process.cwd() + '/uber/static/deps/selectToAutocomplete/jquery.select-to-autocomplete.js'
                        ]);
                    } else if (component === 'jquery') {
                        // jquery-datetextentry doesn't have a bower.json so we manually add it
                        // TODO: make a pull request to the jquery-datetextentry to give them bower support
                        return mainFiles.concat([
                            process.cwd() + '/uber/static/deps/jquery-datetextentry/jquery.datetextentry.js',
                            process.cwd() + '/uber/static/deps/jquery-datetextentry/jquery.datetextentry.css'
                        ]);
                    } else if (component === 'datatables') {
                        mainFiles = mainFiles.map(function(filepath) {
                            return filepath.replace('jquery.dataTables.css', 'dataTables.bootstrap.css')
                        });
                        mainFiles = mainFiles.concat([process.cwd() + '/bower_components/datatables/media/js/dataTables.bootstrap.js']);
                        return mainFiles;
                    } else {
                        return mainFiles;
                    }
                }
            }
        },
        uglify: {
            options: {
                mangle: false,
                output: { comments: 'some' },
                sourceMap: true
            },
            target: {
                files: {
                    'uber/static/deps/combined.min.js': ['uber/static/deps/combined.js']
                }
            }
        },
        cssmin: {
            options: {
                sourceMap: true
            },
            target: {
                files: {
                    'uber/static/deps/combined.min.css': ['uber/static/deps/combined.css']
                }
            }
        }
    });
    grunt.loadNpmTasks('grunt-bower-concat');
    grunt.loadNpmTasks('grunt-contrib-uglify');
    grunt.loadNpmTasks('grunt-contrib-cssmin');
    grunt.registerTask('default', ['bower_concat', 'uglify', 'cssmin']);
};
